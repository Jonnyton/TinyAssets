## ADDED Requirements

### Requirement: Singleton LanceDB Vector Store

The system SHALL expose the LanceDB connection through a single module-global object (in `tinyassets.retrieval.vector_store`) that is created once and reused for every caller, guarded by a lock so concurrent callers share one connection. The connection SHALL be reopened only when the requested path differs from the currently connected path (or none is open yet), never recreated per call. The connection factory and the `VectorStore` wrapper SHALL refuse an empty path by raising `ValueError`, because a CWD-relative default would let two universes read and write each other's vectors. Embeddings SHALL be supplied as pre-computed numeric vectors; the vector store SHALL NOT call an embedding model itself.

#### Scenario: One connection is reused for the same path

- **WHEN** two callers request the vector-store connection for the same database path
- **THEN** both receive the identical connection object rather than a freshly opened one

#### Scenario: Empty path is refused as a contamination guard

- **WHEN** a caller requests the connection or constructs a `VectorStore` with an empty path
- **THEN** the call raises `ValueError` naming the cross-universe contamination risk and no connection is opened

#### Scenario: Search takes a pre-computed embedding

- **WHEN** a caller searches with a pre-computed query vector
- **THEN** matching chunks are returned ranked by distance and the internal seed row is excluded from the results

### Requirement: Path-Explicit Knowledge Graph With Scope Columns

The system SHALL persist the knowledge graph (entities, edges, facts, communities) in a per-universe SQLite database file named `knowledge.db`, opened in WAL mode by `tinyassets.knowledge.knowledge_graph.KnowledgeGraph`. The graph SHALL require an explicit `db_path` and SHALL raise `ValueError` on an empty path, mirroring the vector-store contamination guard. On initialization the schema SHALL idempotently ensure four scope columns (`universe_id`, `goal_id`, `branch_id`, `user_id`) and the tag-matrix columns exist on every scoped table, adding any that are missing without disturbing existing rows, and SHALL create a composite scope index for the hot read path. An igraph graph SHALL be constructed on demand from the stored relationships to serve Leiden community detection and HippoRAG Personalized PageRank; the knowledge graph is not a shared singleton and each instance owns its own SQLite connection.

#### Scenario: Empty db_path is refused

- **WHEN** a `KnowledgeGraph` is constructed with an empty `db_path`
- **THEN** construction raises `ValueError` naming the contamination risk and no database is opened

#### Scenario: Scope columns are ensured idempotently

- **WHEN** a knowledge graph is initialized against a database whose scoped tables predate the scope columns
- **THEN** the missing `universe_id`/`goal_id`/`branch_id`/`user_id` columns are added while existing rows are preserved, and re-initializing the same database makes no further schema changes

### Requirement: Hybrid Multi-Backend Retrieval Router

The system SHALL provide an agentic retrieval router (`tinyassets.retrieval.router.RetrievalRouter`) that decomposes a natural-language query into sub-queries and routes each to the backend suited to its query type: entity/relationship queries to HippoRAG Personalized PageRank over the knowledge graph, thematic/global queries to the RAPTOR summarization tree, and tone/similarity queries to the LanceDB vector store. Decomposition SHALL use the configured LLM provider when available and SHALL fall back to a deterministic rule-based decomposition when no provider is configured or the provider call fails. Routing SHALL be phase-aware, skipping any backend not enabled for the current graph phase, and the merged result SHALL be de-duplicated by clustering near-identical facts and passages before it is returned.

#### Scenario: Query type selects the backend

- **WHEN** a query is decomposed into an entity/relationship sub-query and a tone/similarity sub-query for a phase that enables both backends
- **THEN** the entity/relationship sub-query is served from HippoRAG and the tone/similarity sub-query is served from the vector store, and the result records both backends as sources

#### Scenario: Decomposition falls back without an LLM

- **WHEN** the router runs with no provider callable configured
- **THEN** the query is decomposed by the rule-based fallback and routed by keyword-inferred query type rather than failing

#### Scenario: Phase gating skips a disabled backend

- **WHEN** a sub-query would route to a backend that the current phase does not enable
- **THEN** that backend is not queried and contributes no rows to the result

### Requirement: Scope-Isolation Defense-In-Depth On Retrieval

Every router query SHALL require a `MemoryScope` and SHALL apply a post-retrieval assertion that drops any returned row whose declared `universe_id` disagrees with the caller's scope, logging a loud warning that identifies the offending field and the caller scope because such a mismatch signals a backend singleton bleed. Rows that carry no scope metadata, or whose scope tier is the empty-string null-equivalent, SHALL pass through unchanged so legacy and universe-public rows are not dropped. Enforcement of the sub-tiers (`goal_id`, `branch_id`, `user_id`) SHALL be gated behind the `TINYASSETS_TIERED_SCOPE` environment flag, which defaults off; with the flag off only `universe_id` is enforced. As-built limitation: knowledge-graph and vector rows are path-tagged per universe rather than universally row-tagged, so this read-side check is defense-in-depth over per-universe physical isolation, not the sole isolation mechanism.

#### Scenario: Cross-universe row is dropped and logged

- **WHEN** a retrieval result contains a row whose declared `universe_id` differs from the caller's scope
- **THEN** the row is removed from the result and a warning is logged naming the caller scope and the mismatch

#### Scenario: Untagged row passes through

- **WHEN** a retrieval result contains a row with no `universe_id` attribute or an empty-string tier value
- **THEN** the row is retained rather than dropped by the scope assertion

#### Scenario: Sub-tier enforcement is flag-gated

- **WHEN** `TINYASSETS_TIERED_SCOPE` is off and a row's `branch_id` differs from the caller's `branch_id` while its `universe_id` matches
- **THEN** the row is retained, because sub-tier enforcement is active only when the flag is on

### Requirement: Tiered Memory Scope Model

The system SHALL model memory visibility (`tinyassets.memory.scoping.MemoryScope`) as five orthogonal tiers — universe, goal, branch, user, and node — where universe is a hard invariant that no read or write may cross, and each other tier acts as an independent filter whose `None` value means "not scoped to a specific value on this tier." Four of the tiers (universe, goal, branch, user) SHALL be the columns persisted on scoped memory tables; the node tier SHALL express per-execution breadth and declared external sources rather than a stored column. As-built limitation: the write-side tagging shape is present, but flipping the read-side sub-tier predicate on for all callers is gated behind `TINYASSETS_TIERED_SCOPE` (the Stage 2c flag), which is off by default.

#### Scenario: Universe is a hard boundary

- **WHEN** any caller composes a scope predicate
- **THEN** the universe tier is always present and constrains the query, independent of which optional tiers are set

#### Scenario: Unset tier means unconstrained on that tier

- **WHEN** a caller's scope leaves the goal, branch, or user tier as `None`
- **THEN** that tier imposes no constraint and rows at any value of that tier remain visible subject to the other tiers

### Requirement: Unified Per-Universe Notes With Status Lifecycle

The system SHALL store all feedback for a universe as a single `notes.json` file (`tinyassets.notes`), where each note declares a `source` of `user`, `editor`, `structural`, or `system`, a `category` of `protect`, `concern`, `direction`, `observation`, or `error`, and a `status` that advances through the lifecycle `unread` → `read` → `acted_on` or `dismissed`. A status update SHALL be rejected when the target status is not one of the four defined values. Unread notes assembled for the orient phase SHALL be ordered by priority with errors first, then concerns, directions, observations, and protects last.

#### Scenario: Note round-trips with its typed fields

- **WHEN** a note is written with a source, category, and text and then loaded back
- **THEN** the loaded note preserves its source, category, text, and default `unread` status

#### Scenario: Invalid status is rejected

- **WHEN** a caller attempts to set a note's status to a value outside `unread`/`read`/`acted_on`/`dismissed`
- **THEN** the update is refused and the note's status is unchanged

#### Scenario: Orient notes are priority-ordered

- **WHEN** unread notes of mixed categories are gathered for the orient phase
- **THEN** they are returned with error notes before concerns, concerns before directions, and observations and protects last

### Requirement: Host-Local Daemon Learning Wiki With Bounded Caps

The system SHALL maintain a host-local learning wiki per soul-bearing daemon (`tinyassets.daemon_wiki`), rooted under a `daemon_wikis/<daemon-slug>` directory, composed of immutable raw signal records, maintained synthesis pages, and a schema page describing how future runs use the wiki. Scaffolding and signal recording SHALL be refused for a daemon without a soul by raising `ValueError`. Wiki growth SHALL be bounded by an age-scaled byte cap that starts at a first-month cap and interpolates toward a plateau cap (default 16 MiB rising toward 64 MiB for a user daemon and 128 MiB for a project daemon), and a compaction pass SHALL prune content when the total exceeds the effective cap. Wiki contents and absolute paths SHALL be treated as host-local and SHALL NOT be published to public platform surfaces. As-built limitation: automatic verdict-feedback trigger wiring and the end-to-end autoresearch closed-loop proof are deferred pending BUG-049 terminal-run evidence, so the closed loop is documented but not yet automated.

#### Scenario: Soul-bearing daemon gets a scaffolded host-local wiki

- **WHEN** a soul-bearing daemon records or reads its wiki for the first time
- **THEN** the schema page, index, and core synthesis pages are created under the daemon's host-local wiki root

#### Scenario: Soulless daemon has no learning wiki

- **WHEN** a caller attempts to scaffold or record a signal for a daemon that has no soul
- **THEN** the operation raises `ValueError` and no wiki is created

#### Scenario: Over-cap wiki is compacted

- **WHEN** the wiki's total byte size exceeds its effective age-scaled cap
- **THEN** the compaction pass prunes content toward the cap and reports whether the wiki remains over cap
