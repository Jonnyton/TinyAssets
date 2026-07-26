## MODIFIED Requirements

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

## ADDED Requirements

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
