# Knowledge Retrieval and Memory

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

The RAG/memory backbone for long-horizon daemon work: hybrid retrieval (SQLite knowledge graph, HippoRAG, RAPTOR, singleton LanceDB vectors), tiered memory scopes, unified per-universe notes, and the bounded daemon learning-wiki.

## Requirements

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

The system SHALL model scoped memory visibility (`tinyassets.memory.scoping.MemoryScope`) as five orthogonal tiers—universe, goal, branch, user, and node—where universe is a hard invariant for every read or write that uses this scope model, and each other tier acts as an independent filter whose `None` value means “not scoped to a specific value on this tier.” Four tiers (universe, goal, branch, user) SHALL be available as columns on scoped memory tables; the node tier SHALL express per-execution breadth and declared external sources rather than a stored column. As-built limitations: the write-side tagging shape exists, but the read-side sub-tier predicate is gated behind `TINYASSETS_TIERED_SCOPE` and defaults off; legacy fantasy chapter-learning rules use a separate process-global in-memory store with no universe key and therefore do not inherit this isolation guarantee.

#### Scenario: Universe is a hard boundary for a scoped predicate

- **WHEN** a caller composes a predicate from a `MemoryScope`
- **THEN** the universe tier is always present and constrains the query, independent of which optional tiers are set

#### Scenario: Unset tier means unconstrained on that tier

- **WHEN** a caller's scope leaves the goal, branch, or user tier as `None`
- **THEN** that tier imposes no constraint and rows at any value of that tier remain visible subject to the other tiers

#### Scenario: Legacy learning is outside the scoped-store guarantee

- **WHEN** two fantasy universes execute chapter learning in the same process
- **THEN** the process-global rule set is not separated by `MemoryScope`, and the scoped-store universe invariant MUST NOT be inferred for those rules

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

### Requirement: Soul-Scoped Host-Local Mini-Brain Store

The system SHALL maintain `daemon_brain.db` as a host-local SQLite store of typed entries, FTS rows, memory events, and promotion records for soul-bearing daemons only. Capture SHALL normalize whitespace, deduplicate equal content fingerprints within one daemon while refreshing the existing row, keep identical content in different daemons isolated, clamp confidence and importance to `[0,1]`, and preserve typed provenance, reliability, temporal, sensitivity, visibility, lifecycle, and metadata fields. The accepted kind registry SHALL include semantic, episodic, procedural, policy, claim, preference, failure mode, open loop, contradiction, soul proposal, session trace summary, and experience lesson entries.

#### Scenario: Soulless capture is refused

- **WHEN** a caller captures a mini-Brain entry for a daemon without a soul
- **THEN** capture raises `ValueError` and writes no entry

#### Scenario: Deduplication is per daemon

- **WHEN** normalized content is captured twice for one daemon and once for a different daemon
- **THEN** the first daemon reuses one entry while the second daemon receives an independent entry

### Requirement: Explicit Mini-Brain Review And Wiki-Promotion Lifecycle

The system SHALL validate mini-Brain review transitions among `candidate`, `accepted`, `promoted`, `rejected`, and `superseded`, record reviewer notes and transition history, emit typed events, and require same-daemon replacement entries through the validated review and direct-supersede paths. Wiki promotion SHALL validate daemon ownership and a safe relative page path, mark the selected entries promoted, record the promotion, and append a curated summary plus entry content to that daemon's host-local wiki. As-built limitations: capture accepts an arbitrary `supersedes_entry_id` and can retain a dangling or cross-daemon lineage identifier even though it only updates a matching same-daemon predecessor; reviewer identity is caller-supplied rather than authenticated; some direct supersession helpers bypass part of the transition validator; and the SQLite commit occurs before the wiki append, so a filesystem failure can leave promoted database state without its rendering.

#### Scenario: Terminal rejection cannot promote through review

- **WHEN** a rejected entry is submitted to the validated promotion path
- **THEN** the transition is refused and no wiki promotion is recorded

#### Scenario: Unsafe wiki path is refused

- **WHEN** promotion names a page outside the daemon wiki through an absolute or traversing path
- **THEN** the operation raises `ValueError` before appending wiki content

### Requirement: Per-Daemon Mini-Brain Retrieval And Bounded Injection

The system SHALL expose search addressed to exactly one daemon, using FTS5 text matching with a token-`LIKE` fallback after an FTS operational failure, recent-important ordering for an empty query, and optional caller-supplied embeddings for LanceDB vector hits. Search SHALL support kind and visibility filters, exclude rejected and superseded relational rows by default, clamp the score threshold, cap results at 50, and emit query and retrieve events under one trace plus a low-confidence event when a non-empty query has no result clearing the threshold. Prompt-packet assembly SHALL render selected hits under the caller's exact character cap and emit an injection event. As-built limitations: ordinary search may return unreviewed candidates or host-private entries; visibility is a filter tag rather than authorization; vector indexing is optional/non-transactional, and vector-only hits may bypass relational lifecycle filters.

#### Scenario: Search remains daemon-local

- **WHEN** matching content exists only for another daemon
- **THEN** the addressed daemon's search and prompt packet omit that content

#### Scenario: Packet obeys its character budget

- **WHEN** matching entries exceed the requested packet length
- **THEN** the rendered packet is truncated so its character length never exceeds the cap

### Requirement: Caller-Owned Mini-Brain Quality Replay

The system SHALL evaluate memory contribution by building one packet, invoking a caller-provided replay function once with memory and once without it, and scoring the result with either expected-signal matching or a caller-provided score function. It SHALL classify the delta as `improved`, `regressed`, or `unchanged` and record an eval event without automatically accepting, rejecting, promoting, or deleting any entry. As-built limitation: replay determinism and isolation are caller responsibilities, and the harness does not itself invoke a separate evaluator model.

#### Scenario: Missing scoring contract is refused

- **WHEN** quality replay is requested without expected signals or a score function
- **THEN** the call raises `ValueError` rather than inventing a quality result

#### Scenario: Evaluation has no lifecycle side effect

- **WHEN** a replay produces a positive score delta
- **THEN** an `improved` result and eval event are returned while entry lifecycle states remain unchanged

### Requirement: Mini-Brain Dispatch Hints And Status Surfaces

The system SHALL read dispatch hints through a read-only database connection and return only accepted or promoted `policy`, `preference`, `failure_mode`, or `claim` entries tagged `borrowable_role_context` or `published`. Hint reads SHALL emit no memory events and SHALL contribute only a bounded advisory dispatch-score term. The cost-ledger and global open-Brain status surfaces SHALL open existing databases read-only, expose a rough `len/4` token-cost estimate without making retention decisions, and degrade to `ledger_available=false` when a daemon's mini-Brain database is absent. As-built limitation: the separate per-daemon observability-count surface uses the normal connector and may create and initialize an absent database before returning counts.

#### Scenario: Private candidate does not influence dispatch

- **WHEN** the only task-matching entry is candidate-state or host-private
- **THEN** the read-only dispatch-hint reader omits it and writes no event

#### Scenario: Missing database degrades cleanly on the read-only ledger surface

- **WHEN** the cost-ledger or global open-Brain status is requested before a soul daemon has a mini-Brain database
- **THEN** that read-only surface reports the ledger unavailable rather than creating a database or failing

### Requirement: Bounded Combined Daemon Memory Packet

The system SHALL build a host-local memory packet only for a soul-bearing daemon, scaffold its daemon wiki, and by default run cap enforcement before reading context. It SHALL render a bounded soul capsule followed by existing wiki pages in the fixed priority order `WIKI.md`, `index.md`, decision policy, current self, blocked patterns, review, compaction summary, learning signals, and soul-evolution proposals. When enabled and space remains, it SHALL append a Mini-Brain section using either the supplied query or the daemon-derived default, bounded by both the packet remainder and the Mini-Brain character cap. The returned envelope SHALL keep total context within the requested character cap and include wiki status, truncation, compaction, and Mini-Brain metadata. As-built limitation: default `enforce_cap=true` can mutate the wiki through compaction, so packet construction is not a read-only operation.

#### Scenario: Combined packet obeys its total cap

- **WHEN** the soul capsule, priority wiki pages, and selected Mini-Brain context exceed the requested packet length
- **THEN** the returned combined context never exceeds that character cap and reports truncation metadata

#### Scenario: Default cap enforcement may compact before reading

- **WHEN** packet construction uses its default cap-enforcement setting for an over-cap daemon wiki
- **THEN** it runs wiki compaction before assembling context and returns the compaction result in the packet envelope

### Requirement: Domain-Neutral Episodic SQLite Lifecycle

The system SHALL provide a universe-bound episodic SQLite store for generic domain/episode/sequence summaries, episode summaries, facts with accumulated evidence, observations, and reflections, plus fantasy chapter-window eviction of `scene_summaries`. It SHALL allow a dry-run domain-neutral schema assessment without a migration flag; require `TINYASSETS_EPISODIC_SCHEMA_MIGRATION=1` only for the mutating in-place rewrite; create a backup before mutation; run a no-bleed check after rewrite; and restore the backup when an exception escapes the migration. As-built limitations: a reported `no_bleed_ok=false` result does not itself raise or trigger rollback; direct reads constrain universe but not goal/branch/user tiers; repeated equal sources can increase evidence repeatedly; `mark_promoted` only flips a fact marker; eviction deletes scene summaries only; and legacy fantasy-coordinate methods remain.

#### Scenario: Migration flag is required

- **WHEN** a caller requests a mutating in-place domain-neutral rewrite and the migration flag is not enabled
- **THEN** mutation is refused without rewriting the database, while dry-run assessment remains available

#### Scenario: Failed migration restores its backup

- **WHEN** an enabled in-place migration raises after its backup is created
- **THEN** the original database is restored and the failure propagates

### Requirement: Fantasy Phase Context Assembly And Persistence

The system SHALL provide the fantasy `MemoryManager` with phase-specific orient, plan, draft, and evaluate context bundles assembled from core, episodic, and archival memory. It SHALL estimate tokens at approximately four characters each, trim in three passes, raise `ContextBundleOverflowError` when mandatory content still exceeds the hard budget, store scene summaries/facts/observations, delegate promotion and reflexion, and evict old summaries. As-built limitations: this manager consumes fantasy `SceneState` fields, an unknown phase assembles orient-shaped content while retaining the unknown phase label, archival failures degrade to empty/default results, writes omit sub-tier scope, and result persistence can partially commit before a malformed later fact fails.

#### Scenario: Mandatory context cannot fit

- **WHEN** trimming optional and truncatable fields still leaves a bundle over its token budget
- **THEN** assembly raises `ContextBundleOverflowError` instead of silently returning an oversized bundle

#### Scenario: Unknown phase uses the fallback shape

- **WHEN** context is requested for an unrecognized phase name
- **THEN** the manager returns orient-shaped content while the bundle's phase value remains the caller's unrecognized name

### Requirement: Project-Scoped Versioned Key-Value Memory

The system SHALL expose project-memory set/get/list operations backed by WAL-mode SQLite, with one current value per `(project_id,key)`, append-only history, monotonically increasing versions, optional expected-version conflicts, prefix listing, and a caller-configurable size cap that defaults to one megabyte per supplied project identifier. As-built limitations: project identifiers are not ownership-authorized, expected version is ignored for an absent key, compare-and-set is a read-then-upsert rather than one atomic predicate, size accounting mixes SQLite text length with UTF-8 bytes, and `%`/`_` in prefixes retain SQL `LIKE` wildcard semantics.

#### Scenario: Existing-key optimistic conflict is reported

- **WHEN** a caller supplies an expected version that differs from an existing key's current version
- **THEN** the write is refused with a version-conflict result and history is unchanged

#### Scenario: Project identifiers partition reads

- **WHEN** two project identifiers store the same key with different values
- **THEN** each get/list operation returns only the value addressed by its supplied project identifier

### Requirement: Draft Output Version History

The system SHALL store immutable draft-output versions keyed by universe and fantasy book/chapter/scene coordinates, maintain one current pointer, preserve verdict, quality, and metadata, return newest-first history, retry locked writes, and allow rollback by moving the current pointer to an existing version. As-built limitations: rollback creates no new version or audit record, and concurrent next-version allocation is not protected by a compare-and-set predicate.

#### Scenario: Saving a draft advances the current version

- **WHEN** two drafts are saved for the same universe/book/chapter/scene
- **THEN** both immutable rows remain in history and the second version is current

#### Scenario: Rollback changes only the pointer

- **WHEN** a caller rolls back to an existing earlier version
- **THEN** that row becomes current without inserting an additional version row

### Requirement: Node-Scope Manifest Parsing

The system SHALL parse the node-scope YAML shape into node entries that distinguish full-canon access from narrow slices and declared external sources. A missing or empty manifest SHALL default to in-universe full-canon access; `narrow_slice` SHALL require at least one entity, relation, or document identifier; and a non-universe member SHALL require an allowed external-source kind plus identifier. Unknown top-level fields, access modes, source kinds, and malformed entries SHALL raise `NodeScopeManifestError`. As-built limitations: the format defines no schema-version field (so any version declaration is rejected as an unknown top-level field), this is a loader with no production enforcement consumer, and `universe_member` uses ordinary boolean coercion so a non-empty string such as `"false"` is treated as true.

#### Scenario: Narrow slice without identifiers is refused

- **WHEN** a node declares `narrow_slice` access with no entity, relation, or document IDs
- **THEN** manifest parsing raises `NodeScopeManifestError`

#### Scenario: Missing manifest uses the default scope

- **WHEN** the configured manifest file does not exist
- **THEN** the loader returns the default in-universe full-canon manifest rather than failing

### Requirement: Standalone Temporal Fact Library

The system SHALL expose a standalone SQLite temporal-fact library that can assert facts, supersede or invalidate them, query point-in-time/current/history views, report overlapping-window fact pairs, and rebuild an in-memory changed-entity index. As-built limitations: timestamps are compared lexically, current queries can admit a future `valid_from`, conflict SQL has null and branch-filter gaps, values are stringified, supersession does not require the replacement's lineage field to point back, `branches_with_conflicts` returns an empty placeholder, and no production integration or focused test suite proves stronger behavior.

#### Scenario: Point-in-time query uses stored interval bounds

- **WHEN** a fact's lexical `valid_from` is at or before the requested time and its `valid_until` is absent or later
- **THEN** the point-in-time query can return that fact subject to its entity/attribute/branch filters

#### Scenario: Branch-conflict index remains a placeholder

- **WHEN** callers request `branches_with_conflicts` from the in-memory temporal index
- **THEN** the shipped method returns an empty mapping without querying the store

### Requirement: Standalone Consolidation And Candidate Helpers

The system SHALL expose standalone helpers that group facts by exact lowercased entity-and-relationship keys, select the highest-confidence member as the merge base, aggregate evidence/source fields, identify individual observation records meeting an evidence-count threshold, and return in-memory promotion records. As-built limitations: the configured entity tolerance is unused, unique facts are omitted from the duplicate-merge result, observations are filtered rather than grouped by dimension, no helper persists or deletes source rows, promotion records are returned only, and fallback Python-hash identifiers are not stable across processes.

#### Scenario: Exact duplicate group is merged in memory

- **WHEN** multiple facts have the same lowercased entity and relationship
- **THEN** the consolidator returns a merged record based on the highest-confidence fact with aggregated evidence and sources

#### Scenario: Near match is not merged by tolerance

- **WHEN** two entity names are similar but not equal after lowercase normalization
- **THEN** they are not grouped even when the configured tolerance would otherwise suggest a match

### Requirement: Fantasy Chapter Learning Loop

The system SHALL convert chapter scene/editorial observations into exact-dimension style-rule groups, promote an in-memory rule after at least three observations spanning at least two chapters, decay a promoted rule when current acceptance rate falls by at least 0.20, and return rule state plus craft cards to the fantasy learn phase. As-built limitations: observations and scene IDs are not deduplicated before counting; one module-global `LearningSystem` is shared without universe/book keys and is lost on restart; and newly promoted rules also appear in the active-rule list and are serialized twice in that cycle.

#### Scenario: Observation threshold promotes an in-memory rule

- **WHEN** one exact dimension accumulates at least three observations across at least two chapters
- **THEN** its process-global style rule transitions to promoted state and is included in the returned learning output

#### Scenario: Restart loses learned rules

- **WHEN** the process-global learning system is re-created
- **THEN** previously observed and promoted rules are absent because no durable store is read

### Requirement: Heuristic Craft And Criteria Surfacing

The system SHALL return warning craft cards when chapter acceptance is below `0.5`, informational cards from observed or promoted style rules, and criterion suggestions for eligible extracted single words/bigrams that meet the caller's occurrence threshold (default three) in rationales from the current learning call. Extraction SHALL omit built-in stopwords, known dimensions, and words shorter than four characters. As-built limitations: cards and criteria are returned state artifacts rather than durable Brain memory or evaluator registration, term repetitions inside one rationale count separately, and per-call card IDs are stripped during fantasy learn-phase serialization.

#### Scenario: Repeated current-call terms surface a criterion

- **WHEN** an eligible extracted word or bigram reaches the default three counted occurrences across the rationales supplied to one discovery call
- **THEN** the returned learning state includes an informational criterion craft card without registering a durable evaluator criterion

### Requirement: Episodic Promotion Candidate Scan

The system SHALL scan universe-scoped episodic facts, observation dimensions, and supplied ASP violation descriptions against separately configured thresholds that each default to three. It SHALL persist only the qualifying fact's episodic `promoted` marker; style and ASP results SHALL remain repeatable returned candidate dictionaries. As-built limitation: shipped fantasy runtime calls do not supply violation rows, so the ASP candidate path is unit-exercised but not production-fed.

#### Scenario: Fact threshold sets only the episodic marker

- **WHEN** an episodic fact reaches the configured evidence threshold
- **THEN** the scan returns it and sets that row's promoted flag without writing CoreMemory, archival memory, wiki content, or an OKF bundle

#### Scenario: Style candidate remains return-only

- **WHEN** an observation dimension reaches the configured count
- **THEN** the scan returns a style candidate without persisting a promoted style state or destination

### Requirement: Fantasy Reflexion

The system SHALL produce a critique and reflection through the configured global judge-role provider call when available and deterministic templates otherwise, prefer structured editorial notes while accepting legacy feedback, optionally persist the critique/reflection to episodic SQLite, and make recent persisted reflections available to later orient context. Returned keyword-derived weight changes SHALL be advisory values only. As-built limitations: only episodic storage is constructor-injected; `reflect` does not enforce a revert-only gate; callers do not apply the returned weights; and a reflection can persist with empty feedback.

#### Scenario: LLM failure uses deterministic templates

- **WHEN** the configured judge-role provider call is unavailable or fails
- **THEN** reflexion returns template-generated critique and reflection text rather than failing the phase

#### Scenario: Advisory weights are not applied

- **WHEN** critique keywords produce an `updated_weights` mapping
- **THEN** the mapping is returned to the caller but no memory weights are persisted or changed automatically

### Requirement: Memory Tool Placeholder Envelopes

The system SHALL expose the six current `tinyassets.memory.tools` callable envelopes, accept their optional scope inputs, and validate lifecycle-tier progression only in `memory_promote`, but SHALL NOT claim scope enforcement or durable effects that the implementations do not perform. As built, scope inputs are ignored by the placeholder operations; search and conflict calls return empty results; assertion fabricates a response identifier without storing a fact; and promote/forget/consolidate report envelope success without mutating the episodic, temporal, mini-Brain, or OKF stores.

#### Scenario: Placeholder search has no backend query

- **WHEN** a memory-search tool call supplies scope metadata
- **THEN** it returns the shipped empty-result envelope without querying the memory backends

#### Scenario: Placeholder promotion validates progression only

- **WHEN** a promotion tool call has a valid tier progression
- **THEN** it can report success without changing any persisted memory row

### Requirement: OKF v0.1 export reads only the curated wiki source set

The OKF exporter SHALL require an existing wiki root, refuse a target directory
inside that source root, and export only sorted Markdown files beneath
`pages/`. It MUST exclude every `soul.md`, source `index.md` and `log.md`, and
Markdown under `drafts/`, `raw/`, and `daemon-wiki`; it SHALL write only to the
target bundle and MUST NOT add an MCP action or mutate the source wiki.

#### Scenario: Curated pages export without private material

- **WHEN** a wiki contains promoted pages plus soul, draft, raw, and daemon-wiki Markdown
- **THEN** only non-reserved promoted page files become concepts and the report lists privacy-excluded files

#### Scenario: Export target cannot be nested in the source wiki

- **WHEN** the requested target resolves inside the source wiki root
- **THEN** export raises `ValueError` before writing the bundle

### Requirement: OKF export normalizes concepts, links, reserved files, and evidence

Each exported concept SHALL have `type`, `title`, `timestamp`, and
`workflow_original_path` metadata, using the current frontmatter, heading,
slug, or file-mtime fallbacks and preserving non-empty top-level source fields
recognized by the lightweight parser under `workflow_` keys; this is not
lossless YAML round-tripping. The exporter MUST convert resolvable wikilinks to
absolute bundle links, render unresolved wikilinks as plain labels while
reporting them, write root `index.md` with `okf_version: "0.1"`, write dated
root `log.md`, and return a conformance report with concepts, exclusions,
unresolved links, reserved-file validation, issues, and counts. `conformant`
SHALL be the exporter's local structural flag only: it validates generated
reserved-file shapes and parseable concept frontmatter with non-empty `type`,
not complete upstream OKF conformance or canonical-store authority. Unresolved
links, privacy exclusions, and source pages named `index.md` or `log.md` SHALL
be reported but SHALL NOT independently make `conformant` false.

#### Scenario: Metadata and links are normalized into the bundle

- **WHEN** a promoted page has partial frontmatter and links to another exported page
- **THEN** the concept receives required fallback metadata, recognized non-empty top-level source fields are retained under `workflow_` keys, and the link becomes an absolute bundle link

#### Scenario: Unresolved links remain readable and evidenced

- **WHEN** a promoted page links to a target absent from the export set
- **THEN** the rendered body contains the readable label without a link and the report identifies the source and unresolved target

#### Scenario: Bundle reserved files are regenerated

- **WHEN** export completes with zero or more concepts
- **THEN** root `index.md` and `log.md` are written in the current OKF v0.1 shapes and their validation results appear in the report

#### Scenario: Reserved source-name issue is non-fatal

- **WHEN** a promoted source page itself is named `index.md` or `log.md` and no other conformance issue exists
- **THEN** that source page is omitted and reported as an issue while the report remains conformant

#### Scenario: Local conformance is deliberately narrow

- **WHEN** a bundle has valid generated reserved files and parseable concept frontmatter with non-empty types but also has unresolved links or privacy exclusions
- **THEN** the local `conformant` flag remains true and does not claim complete upstream OKF or canonical-store conformance
