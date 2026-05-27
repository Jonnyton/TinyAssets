"""Agentic retrieval router -- decomposes compound queries and routes.

The LLM decides what kind of question is being asked and decomposes
compound queries into sub-queries routed to HippoRAG (entity/relationship),
RAPTOR (thematic/global), or LanceDB vectors (tone/similarity).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import numpy as np

from workflow.knowledge.hipporag import HippoRAG
from workflow.knowledge.knowledge_graph import KnowledgeGraph
from workflow.knowledge.models import (
    FactWithContext,
    QueryType,
    RetrievalResult,
    SubQuery,
)
from workflow.knowledge.raptor import RaptorTree, query_raptor_tree
from workflow.knowledge.tag_matrix import (
    TagMatrixQuery,
    filter_rows_by_tag_matrix,
    row_visible_for_tag_matrix,
)
from workflow.memory.scoping import MemoryScope
from workflow.retrieval.phase_context import should_use_backend
from workflow.retrieval.vector_store import VectorStore
from workflow.utils.json_parsing import parse_llm_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Query decomposition
# ---------------------------------------------------------------------------

DECOMPOSITION_SYSTEM = (
    "You are a query decomposition engine. Given a compound query about "
    "a fantasy narrative, break it into sub-queries. Each sub-query should "
    "be routed to the right retrieval backend.\n\n"
    "Backend types:\n"
    "- entity_relationship: for character/faction relationships, who-knows-what\n"
    "- thematic_global: for big-picture questions spanning chapters/books\n"
    "- tone_similarity: for finding similar prose, voice matching, mood\n\n"
    "Output valid JSON: a list of objects with 'text', 'query_type', 'entity_hints'."
)

DECOMPOSITION_PROMPT = """Decompose this query into sub-queries.

Query: {query}
Phase: {phase}
Context: Retrieving for a {phase} node in a fantasy writing system.

Return JSON list. Example:
[
  {{"text": "Ryn's relationships with Ashwater",
    "query_type": "entity_relationship",
    "entity_hints": ["ryn", "ashwater"]}},
  {{"text": "winter atmosphere in the northern pass",
    "query_type": "tone_similarity", "entity_hints": []}}
]"""


def _parse_decomposition(raw: str) -> list[SubQuery]:
    """Parse LLM decomposition response into SubQuery objects."""
    items = parse_llm_json(raw, expect_type=list, fallback=None)
    if items is None:
        return [SubQuery(text=raw, query_type=QueryType.ENTITY_RELATIONSHIP)]

    return [
        SubQuery(
            text=item.get("text", ""),
            query_type=QueryType(item.get("query_type", "entity_relationship")),
            entity_hints=item.get("entity_hints", []),
        )
        for item in items
        if isinstance(item, dict)
    ]


def _simple_decompose(query: str) -> list[SubQuery]:
    """Rule-based fallback decomposition (no LLM needed).

    Useful for testing or when the LLM is unavailable.
    """
    query_lower = query.lower()

    # Detect query type from keywords
    if any(kw in query_lower for kw in ["relationship", "knows", "alliance", "faction", "who"]):
        return [SubQuery(text=query, query_type=QueryType.ENTITY_RELATIONSHIP)]
    elif any(kw in query_lower for kw in ["theme", "arc", "overall", "summary", "global"]):
        return [SubQuery(text=query, query_type=QueryType.THEMATIC_GLOBAL)]
    elif any(kw in query_lower for kw in ["tone", "voice", "mood", "atmosphere", "prose", "style"]):
        return [SubQuery(text=query, query_type=QueryType.TONE_SIMILARITY)]
    else:
        return [SubQuery(text=query, query_type=QueryType.ENTITY_RELATIONSHIP)]


# ---------------------------------------------------------------------------
# Phase-aware retrieval methods
# ---------------------------------------------------------------------------

# Map retrieval source names to backend query types
_SOURCE_TO_BACKEND: dict[str, str] = {
    "kg_relationships": "hipporag",
    "active_promises": "kg",
    "world_state": "kg",
    "episodic_recent": "kg",
    "outline_position": "raptor",
    "orient_warnings": "state",
    "style_rules": "kg",
    "craft_cards": "raptor",
    "genre_conventions": "raptor",
    "voice_examples": "vector",
    "dialogue_patterns": "vector",
    "sensory_details": "vector",
    "character_voice_profiles": "vector",
    "recent_prose": "vector",
    "canon_facts": "kg",
    "world_rules": "kg",
    "knowledge_boundaries": "kg",
    "world_state_timeline": "kg",
    "location_checks": "kg",
}


# ---------------------------------------------------------------------------
# RetrievalRouter
# ---------------------------------------------------------------------------


class RetrievalRouter:
    """Agentic retrieval router with phase-aware context assembly.

    This is the primary interface consumed by the graph-core orient node:
        ``router.query(query, phase, access_tier) -> RetrievalResult``

    Parameters
    ----------
    kg
        KnowledgeGraph instance.
    vector_store
        LanceDB VectorStore instance.
    raptor_tree
        Built RAPTOR tree (can be None if not yet constructed).
    provider_call
        Async callable for LLM query decomposition.
        ``provider_call(prompt, system, role) -> str``
    embed_fn
        Callable that converts text to embedding vector.
        ``embed_fn(text) -> numpy array``
    """

    def __init__(
        self,
        kg: KnowledgeGraph,
        vector_store: VectorStore | None = None,
        raptor_tree: RaptorTree | None = None,
        provider_call: Callable | None = None,
        embed_fn: Callable | None = None,
    ) -> None:
        self._kg = kg
        self._hipporag = HippoRAG(kg)
        self._vector_store = vector_store
        self._raptor_tree = raptor_tree
        self._provider_call = provider_call
        self._embed_fn = embed_fn

    async def query(
        self,
        query: str,
        phase: str,
        *,
        scope: MemoryScope,
        access_tier: int = 0,
        pov_character: str | None = None,
        chapter_number: int | None = None,
        tag_query: TagMatrixQuery | None = None,
        token_budget: int = 4000,
    ) -> RetrievalResult:
        """Route a query to the appropriate retrieval backends.

        Parameters
        ----------
        query
            The natural-language query.
        phase
            Current graph phase: orient|plan|draft|evaluate.
        scope
            Universe/branch/author scope. Required. Used by the
            post-query assertion to drop any row whose ``universe_id``
            metadata disagrees with ``scope.universe_id`` — a
            defense-in-depth check for singleton-bleed bugs.
        access_tier
            Maximum access tier for epistemic filtering.
        pov_character
            POV character for epistemic filtering.
        chapter_number
            Current chapter for temporal filtering.
        tag_query
            Optional tag-matrix filter. Applied after hard
            ``MemoryScope`` filtering; tags never replace scope.
        token_budget
            Maximum tokens for the assembled context.

        Returns
        -------
        RetrievalResult
            Merged results from all relevant backends, filtered to the
            given scope.
        """
        # Decompose query into sub-queries
        sub_queries = await self._decompose(query, phase)

        # Route each sub-query based on phase config
        result = RetrievalResult()

        for sq in sub_queries:
            if sq.query_type == QueryType.ENTITY_RELATIONSHIP:
                if not should_use_backend(phase, "kg_relationships"):
                    continue
                self._route_to_hipporag(
                    sq, result, chapter_number, access_tier, pov_character
                )
                result.sources.append("hipporag")

            elif sq.query_type == QueryType.THEMATIC_GLOBAL:
                if not should_use_backend(phase, "outline_position"):
                    continue
                self._route_to_raptor(sq, result)
                result.sources.append("raptor")

            elif sq.query_type == QueryType.TONE_SIMILARITY:
                if not should_use_backend(phase, "voice_examples"):
                    continue
                self._route_to_vector(sq, result, scope, tag_query)
                result.sources.append("vector")

        # Defense-in-depth: drop rows whose declared universe_id
        # disagrees with the caller's scope. Rows without a universe_id
        # attribute pass through (Stage 1 — interface only; KG/vector
        # rows are path-tagged, not row-tagged, today).
        result = _drop_cross_universe_rows(result, scope)
        if tag_query is not None:
            result = _filter_by_tag_matrix(result, scope, tag_query)
            result.sources.append("tag_matrix")

        # Cluster similar results to reduce redundancy
        result = self._cluster_results(result)

        # Estimate token count
        result.token_count = self._estimate_tokens(result)

        return result

    async def _decompose(self, query: str, phase: str) -> list[SubQuery]:
        """Decompose a query into sub-queries using LLM or fallback."""
        if self._provider_call is not None:
            prompt = DECOMPOSITION_PROMPT.format(query=query, phase=phase)
            try:
                raw = await self._provider_call(
                    prompt, DECOMPOSITION_SYSTEM, "extract"
                )
                return _parse_decomposition(raw)
            except Exception:
                pass
        return _simple_decompose(query)

    def _route_to_hipporag(
        self,
        sq: SubQuery,
        result: RetrievalResult,
        chapter_number: int | None,
        access_tier: int,
        pov_character: str | None,
    ) -> None:
        """Route an entity/relationship query to HippoRAG."""
        hippo_result = self._hipporag.query(
            entity_mentions=sq.entity_hints if sq.entity_hints else [sq.text],
            chapter_number=chapter_number,
            access_tier=access_tier,
            pov_character=pov_character,
        )
        result.facts.extend(hippo_result.get("related_facts", []))
        result.relationships.extend(hippo_result.get("related_edges", []))

    def _route_to_raptor(self, sq: SubQuery, result: RetrievalResult) -> None:
        """Route a thematic/global query to RAPTOR."""
        if self._raptor_tree is None:
            return
        if self._embed_fn is None:
            # Can't query without embeddings -- return top-level summaries
            result.community_summaries.extend(
                self._raptor_tree.query_top_level()
            )
            return

        query_emb = self._embed_fn(sq.text)
        summaries = query_raptor_tree(
            self._raptor_tree, query_emb, top_k=3
        )
        result.community_summaries.extend(summaries)

    def _route_to_vector(
        self,
        sq: SubQuery,
        result: RetrievalResult,
        scope: MemoryScope,
        tag_query: TagMatrixQuery | None,
    ) -> None:
        """Route a tone/similarity query to LanceDB vectors."""
        if self._vector_store is None or self._embed_fn is None:
            return

        query_emb = self._embed_fn(sq.text)
        if isinstance(query_emb, np.ndarray):
            query_emb = query_emb.tolist()

        matches = self._vector_store.search(query_emb, limit=5)
        for match in matches:
            if tag_query is not None and not row_visible_for_tag_matrix(
                match, scope=scope, query=tag_query,
            ):
                continue
            result.prose_chunks.append(match.get("text", ""))

    def _cluster_results(self, result: RetrievalResult) -> RetrievalResult:
        """Cluster semantically similar retrieval results.

        Groups facts and prose chunks that are near-duplicates, keeping
        the highest-importance representative from each cluster.  Uses
        embedding cosine similarity when an embed_fn is available,
        otherwise falls back to text overlap ratio.
        """
        if len(result.facts) > 1:
            result.facts = _cluster_facts(result.facts, self._embed_fn)
        if len(result.prose_chunks) > 1:
            result.prose_chunks = _cluster_texts(
                result.prose_chunks, self._embed_fn
            )
        if len(result.community_summaries) > 1:
            result.community_summaries = _cluster_texts(
                result.community_summaries, self._embed_fn
            )
        return result

    def _estimate_tokens(self, result: RetrievalResult) -> int:
        """Rough token count estimate (4 chars per token)."""
        total_chars = 0
        for f in result.facts:
            total_chars += len(f.text)
        for r in result.relationships:
            total_chars += 50  # Approximate per relationship
        for chunk in result.prose_chunks:
            total_chars += len(chunk)
        for summary in result.community_summaries:
            total_chars += len(summary)
        return total_chars // 4


# ---------------------------------------------------------------------------
# Scope defense-in-depth
# ---------------------------------------------------------------------------


# Memory-scope Stage 2b.3: the four tiers the scope assertion inspects.
# ``universe_id`` is always enforced (Stage 1 behavior, cross-universe
# bleeds must always drop). The other three are gated on
# ``WORKFLOW_TIERED_SCOPE`` — flag OFF preserves 2b.2-era behavior of
# universe-only enforcement; flag ON extends the check to every tier
# the caller is pinned at.
_SCOPE_TIER_FIELDS: tuple[str, ...] = (
    "universe_id", "goal_id", "branch_id", "user_id",
)


def tiered_scope_enabled() -> bool:
    """Read ``WORKFLOW_TIERED_SCOPE``. Default OFF. Stage 2b.3 flag.

    When OFF, read-side assertion only drops cross-universe rows
    (2b.2-era behavior). When ON (future 2c), every pinned tier is
    checked — a caller scoped to ``branch_id='main'`` drops rows
    tagged for any other branch.
    """
    value = os.environ.get("WORKFLOW_TIERED_SCOPE", "off")
    return value.strip().lower() in {"on", "1", "true", "yes"}


def _row_tier_value(row: Any, field: str) -> str | None:
    """Return the row's declared value for ``field`` or None if absent.

    Works for dataclass rows (``getattr``), dict rows (``get``), and
    string rows (always None — strings carry no scope metadata).
    Empty strings are treated as missing/legacy values (LanceDB uses
    "" as the string-null equivalent for its scope columns).
    """
    if isinstance(row, str):
        return None
    if isinstance(row, dict):
        value = row.get(field)
    else:
        value = getattr(row, field, None)
    if value is None or value == "":
        return None
    return str(value)


def assert_scope_match(row: Any, caller_scope: MemoryScope) -> bool:
    """Stage-1 assertion extended to all four scope tiers.

    Returns True if the row is visible at ``caller_scope``. A row is
    visible when every tier the caller is pinned at either:
      - is absent/NULL on the row (legacy or universe-public row), or
      - matches the caller's value for that tier.

    ``universe_id`` mismatch always drops the row (Stage 1 hard
    invariant). The sub-tiers (``goal_id`` / ``branch_id`` /
    ``user_id``) are only enforced when ``WORKFLOW_TIERED_SCOPE`` is
    on — flag OFF keeps 2b.2-era behavior for the sub-tiers (they
    pass through even on mismatch).
    """
    # universe_id: always enforced.
    declared = _row_tier_value(row, "universe_id")
    if declared is not None and declared != caller_scope.universe_id:
        return False
    if not tiered_scope_enabled():
        return True
    # Flag ON: also enforce the three sub-tiers when caller is pinned.
    pinned = (
        ("goal_id", caller_scope.goal_id),
        ("branch_id", caller_scope.branch_id),
        ("user_id", caller_scope.user_id),
    )
    for field, caller_val in pinned:
        if caller_val is None:
            continue
        declared = _row_tier_value(row, field)
        if declared is None:
            continue  # legacy / universe-public row passes through
        if declared != caller_val:
            return False
    return True


def _drop_cross_universe_rows(
    result: RetrievalResult, scope: MemoryScope,
) -> RetrievalResult:
    """Drop any row whose declared scope tiers disagree with the caller.

    Memory-scope Stage 2b.3 extension: the check now spans all four
    tiers (``universe_id`` / ``goal_id`` / ``branch_id`` / ``user_id``)
    when ``WORKFLOW_TIERED_SCOPE`` is on. When off, only
    ``universe_id`` is enforced — identical behavior to 2b.2.

    Rows without a tier attribute or with an empty-string tier value
    (the LanceDB string-null equivalent) pass through unchanged —
    legacy / universe-public rows should not be dropped by the
    assertion.

    When a mismatch is detected, a loud WARNING is logged with the
    expected scope, the row's declared tier values, and the row's
    provenance field (``facts`` / ``relationships`` / ``prose_chunks``
    / ``community_summaries``). A mismatch is a bug signal — most
    likely a singleton-bleed in ``runtime.knowledge_graph`` where the
    backend got swapped to another universe's DB without the caller
    being aware, or (under the flag) a write-site threading gap.
    """
    dropped_counts: dict[str, int] = {}
    flag_on = tiered_scope_enabled()

    def _filter(rows: list, field_name: str) -> list:
        kept: list = []
        for row in rows:
            if assert_scope_match(row, scope):
                kept.append(row)
                continue
            dropped_counts[field_name] = dropped_counts.get(field_name, 0) + 1
            # Surface the specific tier that drove the drop so the
            # mismatch log is actionable.
            declared_tiers = {
                t: _row_tier_value(row, t)
                for t in _SCOPE_TIER_FIELDS
                if _row_tier_value(row, t) is not None
            }
            logger.warning(
                "retrieval.scope_mismatch: dropped %s row "
                "(caller=%r, row_tiers=%r, tiered_flag=%s)",
                field_name, scope.compose_predicate(),
                declared_tiers, "on" if flag_on else "off",
            )
        return kept

    result.facts = _filter(result.facts, "facts")
    result.relationships = _filter(result.relationships, "relationships")
    result.prose_chunks = _filter(result.prose_chunks, "prose_chunks")
    result.community_summaries = _filter(
        result.community_summaries, "community_summaries",
    )

    if dropped_counts:
        logger.warning(
            "retrieval.scope_mismatch: dropped %d rows across fields %s "
            "(caller_scope=%r, tiered_flag=%s) — likely a backend "
            "singleton bleed or a Stage-2b write-site threading gap",
            sum(dropped_counts.values()),
            sorted(dropped_counts.keys()),
            scope.compose_predicate(),
            "on" if flag_on else "off",
        )

    return result


def _filter_by_tag_matrix(
    result: RetrievalResult,
    scope: MemoryScope,
    tag_query: TagMatrixQuery,
) -> RetrievalResult:
    """Apply CHILD-2 tag-matrix filtering after hard scope checks."""
    before = (
        len(result.facts),
        len(result.relationships),
        len(result.community_summaries),
    )
    result.facts = filter_rows_by_tag_matrix(
        result.facts, scope=scope, query=tag_query,
    )
    result.relationships = filter_rows_by_tag_matrix(
        result.relationships, scope=scope, query=tag_query,
    )
    result.community_summaries = filter_rows_by_tag_matrix(
        result.community_summaries, scope=scope, query=tag_query,
    )
    after = (
        len(result.facts),
        len(result.relationships),
        len(result.community_summaries),
    )
    dropped = sum(before) - sum(after)
    if dropped:
        logger.info(
            "tag_matrix.filter: dropped %d rows after scope filtering "
            "(caller_scope=%r, domain_tags=%r, shape_tags=%r)",
            dropped,
            scope.compose_predicate(),
            tag_query.domain_tags,
            tag_query.shape_tags,
        )
    return result


# Backward-compat alias — external callers expect ``_row_universe_id``.
def _row_universe_id(row: Any) -> str | None:
    """Compat shim for the 2b.2-era single-tier reader."""
    return _row_tier_value(row, "universe_id")


# ---------------------------------------------------------------------------
# Semantic result clustering
# ---------------------------------------------------------------------------

# Cosine similarity threshold for embedding-based clustering.
_EMBED_SIMILARITY_THRESHOLD = 0.85

# Jaccard overlap threshold for text-based fallback clustering.
# Lower than embedding threshold because Jaccard is stricter on prose.
_TEXT_SIMILARITY_THRESHOLD = 0.70


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _text_overlap(a: str, b: str) -> float:
    """Word-level Jaccard overlap as a fallback similarity measure."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _greedy_cluster(
    texts: list[str],
    embed_fn: Callable | None,
    threshold: float | None = None,
) -> list[list[int]]:
    """Greedy single-pass clustering by pairwise similarity.

    Returns a list of clusters, each containing indices into *texts*.
    The first item in each cluster is the representative.

    When *threshold* is None, the threshold is chosen automatically:
    ``_EMBED_SIMILARITY_THRESHOLD`` when embeddings are available,
    ``_TEXT_SIMILARITY_THRESHOLD`` for text-overlap fallback.
    """
    n = len(texts)
    if n <= 1:
        return [[i] for i in range(n)]

    # Build similarity function.
    # Safety valve: skip embedding calls for large result sets to avoid
    # O(n) sequential API round-trips.  Text-overlap fallback is adequate
    # for dedup at this scale.
    _EMBED_CAP = 100
    embeddings: list[np.ndarray] | None = None
    if embed_fn is not None and n <= _EMBED_CAP:
        try:
            embeddings = [np.asarray(embed_fn(t)) for t in texts]
        except Exception:
            embeddings = None

    if threshold is None:
        threshold = (
            _EMBED_SIMILARITY_THRESHOLD if embeddings is not None
            else _TEXT_SIMILARITY_THRESHOLD
        )

    def similarity(i: int, j: int) -> float:
        if embeddings is not None:
            return _cosine_similarity(embeddings[i], embeddings[j])
        return _text_overlap(texts[i], texts[j])

    assigned = [False] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if assigned[i]:
            continue
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if assigned[j]:
                continue
            if similarity(i, j) >= threshold:
                cluster.append(j)
                assigned[j] = True
        clusters.append(cluster)

    return clusters


def _cluster_facts(
    facts: list[FactWithContext],
    embed_fn: Callable | None,
) -> list[FactWithContext]:
    """Cluster near-duplicate facts, keeping the highest-importance one."""
    if len(facts) <= 1:
        return facts

    texts = [f.text for f in facts]
    clusters = _greedy_cluster(texts, embed_fn)

    result: list[FactWithContext] = []
    for cluster in clusters:
        # Pick the fact with highest importance as representative
        best_idx = max(cluster, key=lambda i: facts[i].importance)
        result.append(facts[best_idx])
    return result


def _cluster_texts(
    texts: list[str],
    embed_fn: Callable | None,
) -> list[str]:
    """Cluster near-duplicate text strings, keeping the longest representative."""
    if len(texts) <= 1:
        return texts

    clusters = _greedy_cluster(texts, embed_fn)

    result: list[str] = []
    for cluster in clusters:
        # Pick the longest text as representative
        best_idx = max(cluster, key=lambda i: len(texts[i]))
        result.append(texts[best_idx])
    return result
