---
status: research
---

# Research Brief: Runtime Fiction Memory Graph — What Would Actually Work Best

Date: 2026-04-09
Status: research complete, ready for implementation session pickup

## Executive Summary

The existing TinyAssets infrastructure is **remarkably close** to frontier research on
structured memory for long-form narrative generation. The project already has
HippoRAG, RAPTOR, LanceDB vector retrieval, a Leiden community-detection layer,
phase-aware context routing, truth-value-typed fact extraction, and a three-tier
memory hierarchy (core/episodic/archival). What is missing is not more retrieval
backends — it is **structured state that accumulates across scenes and gives the
daemon a durable, queryable world model** rather than a growing pile of notes and
extracted facts.

The design note (`2026-04-09-runtime-fiction-memory-graph.md`) and exec plan
already identified the right four-layer decomposition: world truth, event history,
epistemic state, and narrative debt. This brief validates that decomposition
against frontier research, identifies where existing code already covers ground,
and recommends concrete choices for what to build versus what to skip.

---

## 1. What We Already Have (Strengths Worth Preserving)

### Retrieval Stack
- **HippoRAG** (NeurIPS '24): personalized PageRank over the KG with access-tier
  and temporal filtering. This is still frontier — HippoRAG 2 extends it but the
  core pattern is intact.
- **RAPTOR**: recursive abstractive summarization tree for thematic/global queries.
- **LanceDB vector store**: semantic similarity for prose voice and tone.
- **Router + phase_context.py**: agentic query decomposition and phase-aware
  source routing (orient ≠ plan ≠ draft ≠ evaluate). This is a strong design
  that most research papers don't have.

### Knowledge Graph
- **knowledge_graph.py**: SQLite-backed with igraph, entity extraction (LLM +
  regex fallback), access tiers (0–3), temporal scoping, truth-value typing
  (narrator_claim / author_fact / character_belief / world_truth), and narrative
  function classification (foreshadowing / promise / misdirection).
- **Leiden community detection**: character groups, plot threads, factions.
- 449 entities / 617 edges / 220 facts / 256 communities in the Ashwater
  runtime KG.

### Memory Hierarchy
- **CoreMemory**: rebuilt per-node, namespaced key-value context (~15K tokens).
- **EpisodicMemory**: SQLite-backed scene summaries, style observations,
  reflections, promotable facts with evidence thresholds.
- **ArchivalMemory**: bridge to KG (HippoRAG) and ASP constraint system.
- **PromotionGates**: episodic → archival promotion at chapter boundaries.

### Commit Pipeline
- Scene commit already extracts: FactWithContext (with source_type, language_type,
  narrative_function, confidence, access_tier, POV filtering), promises (active /
  resolved / expired), character states (location, emotion, knowledge facts),
  editorial notes (protect / concerns), structural evaluation.
- **WorldStateDB**: SQLite tables for promises, character_states, scene_history,
  extracted_facts.

### What's Missing
The existing KG is entity-and-relationship oriented — great for "who is connected
to whom" queries, but it does not accumulate **scene-level state deltas** or
maintain **temporal ledgers** that the daemon can query for "what changed,"
"what's overdue," or "what does this character believe right now." Notes.json is
a growing stream, not a structured state store.

---

## 2. What Frontier Research Says

### 2a. DOME (NAACL 2025) — Temporal KG + Conflict Detection

**Paper**: "Generating Long-form Story Using Dynamic Hierarchical Outlining with
Memory-Enhancement" (Wang et al., 2025)

**Key idea**: A temporal knowledge graph stores generated content with time-scoped
validity, and an LLM-based conflict detector checks new generation against the
graph before committing.

**Relevance to TinyAssets**: The existing entity KG already has `valid_from_chapter`
and `valid_to_chapter` on edges. DOME validates that this is the right pattern,
but pushes further — every generated scene should **update** the temporal graph
before the next planning step, and the planning step should **query** the graph
for contradictions.

**Recommendation**: TinyAssets should adopt DOME's commit-then-verify cycle. The
existing commit node already extracts facts and updates WorldStateDB; the gap is
that the KG update and contradiction check happen post-commit rather than as a
pre-draft gate. Phase 1 of the exec plan (scene packets) naturally becomes the
DOME-style temporal delta.

### 2b. SCORE (2025) — Dynamic State Tracking + Hybrid Retrieval

**Paper**: "Story Coherence and Retrieval Enhancement for AI Narratives"
(Yi et al., 2025)

**Key idea**: Three-component system: (1) dynamic state tracking via symbolic
logic monitoring objects and characters, (2) context-aware hierarchical episode
summaries, (3) hybrid retrieval combining keyword and semantic search, all
unified through a temporally-aligned RAG pipeline.

**Results**: 23.6% higher coherence, 89.7% emotional consistency, 41.8% fewer
hallucinations vs. baseline GPT.

**Relevance**: TinyAssets already has component (3) via the router, and something
like (2) via episodic memory. The missing piece is **(1) — explicit symbolic state
tracking per entity per scene**. SCORE validates that symbolic state objects
(character location, emotional state, knowledge boundaries) that get updated after
every scene are the single biggest coherence win.

**Recommendation**: The WorldStateDB already tracks character_states with location,
emotional_state, and knowledge_facts. The gap is that these are updated only on
commit and not always checked pre-draft. Making orient query the live symbolic
state (not just notes) and making the plan node validate against it would bring
TinyAssets up to SCORE-level coherence tracking.

### 2c. StoryWriter (ACM CIKM 2025) — Multi-Agent + History Compression

**Paper**: "StoryWriter: A Multi-Agent Framework for Long Story Generation"

**Key idea**: Three agents (outline, planning, writing) with dynamic history
compression — the writing agent compresses story history relative to the current
event, not generically.

**Relevance**: TinyAssets already has orient/plan/draft/commit. The interesting
finding is **event-relative compression** — instead of a sliding window over
recent scenes, compress what's relevant to the current scene's entity
neighborhood and active promises.

**Recommendation**: This aligns with the exec plan's Phase 5 goal of routing
retrieval through typed neighborhoods. The MemoryManager's phase-aware
assembly is already close; the upgrade is replacing the generic "last N scenes"
window with entity- and promise-scoped compression.

### 2d. A-Mem (NeurIPS 2025) — Zettelkasten Agentic Memory

**Paper**: "A-MEM: Agentic Memory for LLM Agents" (Xu et al., 2025)

**Key idea**: Each memory note contains structured attributes (context, keywords,
tags) and is dynamically linked; new memories trigger updates to historical
memories' contextual representations.

**Relevance**: This is conceptually similar to what the exec plan calls "typed
entity records with stable IDs and provenance." A-Mem's key insight is **memory
evolution** — adding a new memory can revise how old memories are indexed. In
fiction terms: learning a character was secretly a spy should retroactively
re-tag all prior scenes involving that character.

**Recommendation**: Build entity records with mutable contextual summaries that
get re-evaluated when major revelations occur. The existing PromotionGates
(fact promotion at chapter boundaries) is the right cadence for this — extend
it to also trigger contextual re-indexing of affected entity records.

### 2e. Letta / MemGPT — Tiered Self-Managed Memory

**Architecture**: Core memory (in-context blocks) + recall memory (recent
searchable) + archival memory (persistent). The agent self-manages what
moves between tiers.

**Relevance**: TinyAssets already has this exact three-tier split
(core/episodic/archival). What Letta adds is that the **agent itself** decides
what to promote or evict, rather than fixed promotion thresholds.

**Recommendation**: Keep the existing threshold-based promotion for now (it's
more deterministic and auditable for fiction), but add an LLM-based "memory
importance scoring" pass at chapter boundaries as Phase 5+ work. The editorial
reader could nominate which facts deserve promotion.

### 2f. GraphRAG / LightRAG / HippoRAG 2 — Graph Retrieval

**GraphRAG** (Microsoft, ICLR '26 benchmark): LLM extracts entity graph,
community detection generates hierarchical summaries, local + global queries.
LazyGraphRAG drops indexing cost to 0.1%.

**LightRAG** (EMNLP 2025): Dual-level retrieval (entity-level + topic-level),
incremental graph updates via union.

**HippoRAG 2**: Improved associativity and sense-making, cheaper offline
indexing.

**Relevance**: TinyAssets already uses HippoRAG + Leiden communities, which
covers the same ground as GraphRAG's community summaries. LightRAG's
incremental update pattern is the most interesting addition — currently
TinyAssets rebuilds the graph per indexing pass; LightRAG shows that
**union-based incremental updates** cut cost by ~50%.

**Recommendation**: Adopt LightRAG-style incremental graph updates for the
entity KG. When a scene commits, union its extracted entities and
relationships into the existing graph rather than re-indexing from scratch.
This becomes critical as universe size grows.

### 2g. MemOS (2025) — Memory as OS Primitive

**Key idea**: Classify memory into parametric (model weights), activation
(in-context attention), and plaintext (external stores). Treat all three as
first-class scheduled resources with API abstraction, permission control,
and proactive preloading ("next-scene prediction").

**Relevance**: The "next-scene prediction" concept is fascinating for
TinyAssets. Instead of only assembling context when orient runs, **precompute
the likely retrieval packet for the next scene** during the commit phase.
The commit node already knows what scene position comes next and what
promises are active — it could pre-stage a retrieval packet.

**Recommendation**: Add a "next-scene context pre-staging" step to the
commit pipeline. When a scene commits and packets are written, also
generate a `next_scene_prefetch.json` with the likely entity neighborhood,
active promises, and relevant recent deltas. Orient can then start from
this rather than querying cold.

---

## 3. Gap Analysis: Existing Design Note vs. Research

| Design Note Layer | Research Validation | Already Built | Gap |
|---|---|---|---|
| World Truth Graph | DOME temporal KG, SCORE symbolic state, GraphRAG entities | Entity KG with access tiers + temporal scoping; WorldStateDB character_states | Need: stable entity IDs, mutable contextual summaries, incremental update |
| Event Graph (scene packets) | DOME scene deltas, StoryWriter event-based outlines | Commit extracts facts, promises, character deltas | Need: structured packet artifact emitted per scene; timeline ledger |
| Epistemic Graph | SCORE dynamic state tracking, existing truth-value typing | FactWithContext has source_type (character_belief, world_truth), KG has access_tier | Need: per-character belief state queryable at any point; reader-known vs. world-true distinction |
| Narrative Debt Graph | SCORE + StoryWriter promise tracking, A-Mem evolution | WorldStateDB promises (active/resolved/expired), orient queries overdue | Need: foreshadowing/mystery/tension tracking beyond promises; explicit debt pressure scoring |
| Retrieval Integration | Phase-aware routing, HippoRAG, RAPTOR, LanceDB | Router + phase_context.py | Need: typed neighborhood queries instead of broad note blobs; pre-staged packets |
| Human-Facing Docs | Generated views (research doesn't focus on this) | Canon markdown pages | Need: regeneration from typed state, not separate truth |

---

## 4. Revised Recommendations for Implementation

### What to Build (High Priority, Validated by Research)

**Phase 1: Scene Commit Packets + Timeline Ledger**
- Emit a structured JSON packet per committed scene (DOME-validated)
- Fields: scene_id, position, POV, time, location, participants, facts_introduced,
  facts_changed, promises (opened/advanced/resolved), relationship_deltas,
  world_state_deltas, epistemic_deltas
- Durable timeline ledger: ordered scene→event index
- This is the backbone everything else builds on

**Phase 2: Promise + Narrative Debt Ledger**
- Extend beyond promises to include: foreshadowing obligations, unresolved
  mysteries, political/faction tensions, relationship pressure, travel logistics
- Add debt pressure scoring (how "overdue" is each obligation)
- StoryWriter and SCORE both validate that explicit obligation tracking is the
  single biggest coherence lever

**Phase 3: Stable Entity Records with Incremental Updates**
- Give every entity a stable ID, typed record, mutable contextual summary,
  provenance chain, and last-changed scene ref
- Adopt LightRAG-style incremental graph union on commit
- A-Mem-style contextual re-indexing when major revelations change entity meaning

**Phase 4: Epistemic State Ledger**
- Per-character: known facts, suspected facts, false beliefs, knowledge sources
- Reader-visible vs. world-true vs. narrator-asserted distinctions
- Queryable at any scene position ("what did Ryn know at scene 12?")
- This is the most novel layer — most research systems collapse everything into
  neutral world state, but this project's existing truth-value typing
  (character_belief / world_truth / narrator_claim) already has the foundation

**Phase 5: Typed Retrieval Routing**
- Replace broad context blobs with entity-neighborhood, promise-neighborhood,
  epistemic-state, and recent-delta slices
- Add next-scene context pre-staging (MemOS "next-scene prediction" pattern)
- Phase-aware assembly already exists; upgrade to typed packet queries

### What to Skip or Defer

- **Full MemGPT-style agent-self-managed memory**: The current threshold-based
  promotion is more deterministic and auditable. Revisit after proving the
  typed state layers work.
- **RAPTOR rebuilds**: The existing RAPTOR tree is fine. Don't rebuild
  summarization trees — focus on the packet/ledger layer.
- **GraphRAG community summaries**: Already covered by Leiden + HippoRAG.
  LazyGraphRAG is interesting but not urgent.
- **New vector store**: LanceDB works. Don't switch.
- **Full backfill of historical universes**: Prove on clean universes first,
  then build backfill tooling.

---

## 5. How Agentic Search Plays In

The existing agentic search (`agentic_search.py` + `router.py`) already
decomposes queries and routes across backends. The upgrade path is:

1. **Add typed ledger backends** to the router alongside KG/RAPTOR/vector:
   - timeline queries → timeline ledger
   - promise/debt queries → narrative debt ledger
   - epistemic queries → epistemic state ledger
   - entity queries → stable entity records (enhanced KG)

2. **Make the router context-aware of scene position**: The router currently
   decomposes based on query semantics. With packets and ledgers, it should
   also know *where* in the story it is and automatically pull the relevant
   temporal neighborhood.

3. **Pre-stage retrieval**: Instead of cold-querying at orient time, the
   commit pipeline pre-assembles the next-scene retrieval packet. Orient
   can then validate and augment rather than build from scratch.

4. **Contradiction detection as a retrieval mode**: Following DOME, add a
   "check for contradictions with X" query type that the plan node can
   invoke before draft, not just post-commit.

---

## 6. Key Architectural Principles (Distilled from Research)

1. **Separate state from prose**: Scene prose is output. Scene packets are
   state. Don't make the daemon re-read prose to understand state.

2. **Temporal all the way down**: Every fact, relationship, and entity state
   should be scoped to the scene/chapter when it was true. Fiction is
   about change over time.

3. **Epistemic asymmetry is a feature, not a bug**: The system must track
   who knows what. Collapsing everything into "world truth" destroys the
   tension that makes fantasy fiction work.

4. **Obligations drive narrative, not just facts**: Promise/debt tracking
   is as important as entity tracking. A daemon that knows all the facts
   but has forgotten what it owes the reader will produce locally clever
   but globally incoherent fiction.

5. **Incremental over batch**: Update the graph on each commit, don't
   rebuild. This follows LightRAG and is critical for long-running
   universes.

6. **Pre-stage context, don't cold-query**: The commit node knows what's
   coming next. Use that knowledge to pre-assemble the next scene's
   retrieval packet.

7. **Typed queries beat broad retrieval**: "Give me everything about the
   current scene" is worse than "give me active promises involving Ryn,"
   "give me location state for Ashwater," "give me what the reader knows
   about the conspiracy."

---

## 7. Sources

### Papers and Frameworks
- [DOME: Dynamic Hierarchical Outlining with Memory-Enhancement](https://arxiv.org/abs/2412.13575) — NAACL 2025
- [SCORE: Story Coherence and Retrieval Enhancement](https://arxiv.org/abs/2503.23512) — 2025
- [StoryWriter: Multi-Agent Framework for Long Story Generation](https://arxiv.org/abs/2506.16445) — ACM CIKM 2025
- [A-Mem: Agentic Memory for LLM Agents](https://arxiv.org/abs/2502.12110) — NeurIPS 2025
- [HippoRAG: Neurobiologically Inspired Long-Term Memory](https://arxiv.org/abs/2405.14831) — NeurIPS 2024
- [GraphRAG: From Local to Global](https://arxiv.org/abs/2404.16130) — Microsoft, ICLR '26
- [LightRAG: Simple and Fast RAG](https://arxiv.org/abs/2410.05779) — EMNLP 2025
- [MemOS: Memory Operating System for LLMs](https://arxiv.org/html/2505.22101v1) — 2025
- [Letta / MemGPT: Agent Memory Architecture](https://www.letta.com/blog/agent-memory) — 2025-2026
- [Long Story Generation via Knowledge Graph and Literary Theory](https://arxiv.org/pdf/2508.03137) — 2025
- [Survey on LLMs for Story Generation](https://aclanthology.org/2025.findings-emnlp.750.pdf) — EMNLP 2025
- [Agentic RAG Survey](https://arxiv.org/abs/2501.09136) — 2025
- [Memory in the Age of AI Agents Survey](https://github.com/Shichun-Liu/Agent-Memory-Paper-List) — 2025
- [Guiding Generative Storytelling with Knowledge Graphs](https://arxiv.org/html/2505.24803v2) — 2025

### Existing Project Artifacts
- `docs/design-notes/2026-04-09-runtime-fiction-memory-graph.md` — original design note
- `docs/exec-plans/active/2026-04-09-runtime-fiction-memory-graph.md` — phased exec plan
- `fantasy_author/knowledge/` — KG, HippoRAG, RAPTOR, Leiden, entity extraction
- `fantasy_author/retrieval/` — router, agentic search, phase context, vector store
- `fantasy_author/memory/` — core/episodic/archival hierarchy, promotion gates
- `fantasy_author/nodes/commit.py` — fact/promise/entity extraction pipeline
- `fantasy_author/nodes/world_state_db.py` — promises, character states, scene history
