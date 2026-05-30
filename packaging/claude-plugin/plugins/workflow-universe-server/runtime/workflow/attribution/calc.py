"""Attribution share calculation — depth-decay credit distribution.

Given a provenance DAG (list of AttributionEdges) rooted at an artifact,
compute normalized credit shares for each artifact in the lineage, then
optionally aggregate by actor using AttributionCredit records.

Decay rule: each generation upstream from the leaf gets half the weight
of the next-newer generation. Leaf = generation 0 (the current artifact).
An author who contributed at generation depth d gets weight 2^(-d).
Authors at the same generation split that generation's weight equally.
Shares are normalized so the total sums to 1.0.
"""

from __future__ import annotations

from workflow.attribution.schema import AttributionCredit, AttributionEdge
from workflow.payments.identifiers import MicroToken

_DEFAULT_DEPTH_CAP = 10


def compute_credit_shares(
    edges: list[AttributionEdge],
    credits: list[AttributionCredit] | None = None,
    depth_cap: int = _DEFAULT_DEPTH_CAP,
) -> dict[str, float]:
    """Compute normalized credit shares from a provenance lineage.

    When `credits` is provided, returns shares keyed by actor_id.
    When `credits` is None, returns shares keyed by artifact_id (parent nodes
    in the edge list, representing contributing upstream artifacts).

    Depth-decay: weight at generation depth d = 2^(-d).
    Authors / artifacts at the same generation split their weight equally.
    Result sums to 1.0 (normalized).

    Raises:
        ValueError: if a cycle is detected in the edge graph.
        ValueError: if edges is empty and credits is None (nothing to compute).
    """
    if not edges and not credits:
        return {}

    if credits is not None:
        return _shares_from_credits(credits, depth_cap)
    return _shares_from_edges(edges, depth_cap)


def _shares_from_credits(
    credits: list[AttributionCredit],
    depth_cap: int,
) -> dict[str, float]:
    """Aggregate shares by actor_id using pre-computed AttributionCredit records."""
    # Group actors by generation depth
    by_depth: dict[int, list[str]] = {}
    for c in credits:
        depth = min(c.generation_depth, depth_cap)
        by_depth.setdefault(depth, []).append(c.actor_id)

    if not by_depth:
        return {}

    # Compute raw weights per actor
    raw: dict[str, float] = {}
    for depth, actors in by_depth.items():
        generation_weight = 2.0 ** (-depth)
        per_actor = generation_weight / len(actors)
        for actor in actors:
            raw[actor] = raw.get(actor, 0.0) + per_actor

    total = sum(raw.values())
    if total <= 0.0:
        return {}
    return {actor: w / total for actor, w in raw.items()}


def _shares_from_edges(
    edges: list[AttributionEdge],
    depth_cap: int,
) -> dict[str, float]:
    """Compute shares keyed by artifact_id from the edge DAG.

    Detects cycles via DFS. Truncates at depth_cap.
    """
    # Build adjacency: child_id → list of parent_ids + their generation depths
    children: dict[str, list[tuple[str, int]]] = {}
    all_artifact_ids: set[str] = set()
    for e in edges:
        children.setdefault(e.child_id, []).append((e.parent_id, e.generation_depth))
        all_artifact_ids.add(e.parent_id)
        all_artifact_ids.add(e.child_id)

    # Find leaf (artifact that never appears as a parent)
    parent_ids = {e.parent_id for e in edges}
    child_ids = {e.child_id for e in edges}
    leaf_candidates = child_ids - parent_ids
    if not leaf_candidates:
        raise ValueError("Cycle detected: no leaf node found in edge graph")

    # Assign generation depths to each artifact (BFS from leaf)
    artifact_depth: dict[str, int] = {}
    visited: set[str] = set()
    queue = [(leaf_id, 0) for leaf_id in leaf_candidates]

    while queue:
        artifact_id, depth = queue.pop(0)
        if artifact_id in visited:
            if artifact_depth[artifact_id] != depth:
                raise ValueError(
                    f"Cycle or conflicting depth detected at artifact {artifact_id!r}"
                )
            continue
        if depth > depth_cap:
            continue
        visited.add(artifact_id)
        artifact_depth[artifact_id] = depth
        for parent_id, edge_depth in children.get(artifact_id, []):
            if parent_id not in visited:
                queue.append((parent_id, depth + 1))

    # Group artifacts by depth (excluding leaf itself at depth 0)
    by_depth: dict[int, list[str]] = {}
    for artifact_id, depth in artifact_depth.items():
        if depth == 0:
            continue  # leaf is the artifact being credited, not a contributor
        by_depth.setdefault(depth, []).append(artifact_id)

    if not by_depth:
        # Only the leaf — original artifact with no parents
        return {}

    # Compute raw weights
    raw: dict[str, float] = {}
    for depth, artifacts in by_depth.items():
        generation_weight = 2.0 ** (-depth)
        per_artifact = generation_weight / len(artifacts)
        for artifact_id in artifacts:
            raw[artifact_id] = per_artifact

    total = sum(raw.values())
    if total <= 0.0:
        return {}
    return {aid: w / total for aid, w in raw.items()}


def compute_payout_shares(
    edges: list[AttributionEdge],
    credits: list[AttributionCredit],
    total_payout: MicroToken,
    fee_pct: float = 0.01,
    depth_cap: int = _DEFAULT_DEPTH_CAP,
) -> dict[str, MicroToken]:
    """Compute per-actor payout amounts after deducting the platform fee.

    Args:
        edges: provenance edges (used when credits is empty).
        credits: per-actor AttributionCredit records for share weighting.
        total_payout: gross payout amount in MicroTokens.
        fee_pct: platform fee fraction (default 1% = 0.01). Routed to treasury.
        depth_cap: max lineage depth.

    Returns:
        dict mapping actor_id → net payout amount in MicroTokens.
        Special key "_treasury" holds the platform fee in MicroTokens.
        All returned amounts are integers, and the result sums exactly to
        `total_payout`.
    """
    gross_total = int(total_payout)
    if gross_total <= 0:
        return {"_treasury": MicroToken(0)}

    shares = compute_credit_shares(edges=edges, credits=credits or None, depth_cap=depth_cap)
    if not shares:
        return {"_treasury": MicroToken(gross_total)}

    fee = int(gross_total * fee_pct)
    distributable = gross_total - fee

    floored_allocations: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    allocated = 0
    for actor_id, share in shares.items():
        raw_payout = distributable * share
        payout = int(raw_payout)
        floored_allocations[actor_id] = payout
        allocated += payout
        remainders.append((raw_payout - payout, actor_id))

    remainder = distributable - allocated
    remainders.sort(key=lambda item: (-item[0], item[1]))
    for _, actor_id in remainders[:remainder]:
        floored_allocations[actor_id] += 1

    result: dict[str, MicroToken] = {"_treasury": MicroToken(fee)}
    for actor_id, payout in floored_allocations.items():
        result[actor_id] = MicroToken(payout)
    return result
