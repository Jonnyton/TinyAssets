## ADDED Requirements

### Requirement: Branch catalog request is closed, bounded, and non-enumerating
The system SHALL expose branch discovery through `read_graph(target="branches")` with individual parameters forming `BranchListRequestV1`. `scope` SHALL be exactly `published` or `mine`, defaulting to `published`; `mine` SHALL require a verified authenticated actor. `query` SHALL be an optional 1–200 character string normalized with Unicode NFKC, surrounding-whitespace trim, and casefold and SHALL match branch names only, never node bodies, prompts, source, state, or wiki content. `tags` SHALL be an optional comma-separated list of at most 16 non-empty values, each NFKC-normalized, trimmed, casefolded, sorted, and deduplicated, with each value at most 64 characters and all supplied tags required to match. `domain_id` and `goal_id` SHALL each be optional trimmed exact-match identifiers of at most 128 characters. `cursor` SHALL be optional and at most 2,048 characters. The handle's existing unset/default `limit=30` SHALL remain observable for this target; an explicitly supplied limit SHALL be an integer in the inclusive range 1–100. Existing shared fields `graph_id`, `run_id`, `branch_id`, `author`, and `run_status` MUST remain empty; any other target-specific field added to the shared handle later MUST remain at its declared default unless this request version explicitly admits it. A violation SHALL return `branch_read_mode_invalid` before catalog access.

`published` SHALL admit only commons branches with an active published version. `mine` SHALL admit only platform-commons branches authored by the verified actor; it MAY include unpublished commons work but SHALL NOT query, proxy, or index content held in a private user-controlled store. Authorization SHALL run before filtering, ordering, cursor evaluation, or projection. There SHALL be no public `all`, `visible`, `include_private`, hidden-total, or universe-membership shortcut.

#### Scenario: Anonymous default lists only active published public branches
- **WHEN** an anonymous caller invokes `read_graph(target="branches")` without a scope
- **THEN** the result contains at most 30 commons branches with active published versions
- **AND** no private, unpublished, or caller-owned-only row is admitted

#### Scenario: Mine requires verified identity
- **WHEN** an anonymous caller requests `scope="mine"`
- **THEN** the call returns `branch_authentication_required` with no branch items

#### Scenario: User-controlled private content is outside the catalog
- **WHEN** a private branch exists only in any actor's user-controlled store
- **THEN** it contributes no item, total, cursor behavior, match count, or other existence evidence to either catalog scope

### Requirement: Branch catalog pagination is authenticated and mutation-explicit
The system SHALL maintain a bounded catalog projection in the canonical branch database containing the allowed summary fields, a candidate active-published-version pointer, and a catalog generation. Branch create and patch SHALL update their projection row and increment the generation in the same database transaction as the branch mutation. Publication writers SHALL emit a durable projection outbox event; the idempotent consumer SHALL update the candidate pointer and generation, and periodic maintenance SHALL reconcile drift. Because the authoritative published version lives outside that transaction, a `published` catalog read MUST verify each returned candidate against the authoritative version store before disclosure and omit stale candidates fail-closed. The read path MAY emit non-mutating telemetry but MUST NOT enqueue or mutate state under the handle's read-only contract. For one request it SHALL examine at most `min(4 * limit, 400)` admitted projection candidates. A returned cursor SHALL advance from the last examined projection row, not the last returned item, and SHALL be present whenever unexamined projection rows remain even if every examined candidate was omitted. The platform `branch_definitions.published` boolean alone MUST NOT establish publication.

The system SHALL order admitted projection rows by `(updated_at DESC, branch_def_id ASC)`. A first page SHALL capture the current branch-catalog generation. Every projection create, patch, publication, unpublication, or deletion SHALL increment that generation in the same canonical database transaction as the projection mutation. `next_cursor` SHALL be a base64url-encoded, versioned AEAD envelope using AES-256-GCM. Its authenticated protected header SHALL contain only `schema_version` and key ID. Its RFC 8785 canonical plaintext SHALL contain issue/expiry times, generation, last ordering tuple, and a SHA-256 context digest over the stable verified actor subject (or fixed `"anonymous"` sentinel), scope, and normalized query/sorted-deduplicated-tags/domain/goal filters. The associated data SHALL be `"branch-list-cursor-v1"` plus the canonical protected header. The token SHALL expire after 10 minutes; active and prior decryption keys SHALL be retained for at least that lifetime. Decoding SHALL enforce the 2,048-character bound before base64/JSON work, authenticate before using plaintext, and reject malformed canonical payloads, unknown key IDs, expired tokens, or invalid tags in one `branch_cursor_invalid` envelope. Keys, plaintext generation, and filter context MUST NOT enter logs or client-visible errors.

An altered token, unknown key version, or cross-principal/scope/filter replay SHALL return `branch_cursor_invalid`. If the catalog generation changed between pages, the call SHALL return `branch_cursor_stale` and require a restart instead of silently duplicating or skipping rows. On an unchanged generation, tied timestamps MUST paginate each admitted row exactly once.

#### Scenario: Tied updates paginate exactly once
- **WHEN** more than one admitted branch has the same `updated_at`, the catalog does not mutate, and the caller follows `next_cursor`
- **THEN** `(updated_at DESC, branch_def_id ASC)` produces each admitted branch exactly once

#### Scenario: Cursor cannot cross actors or filters
- **WHEN** a cursor is altered or replayed under a different actor, scope, or normalized filter set
- **THEN** the call returns `branch_cursor_invalid` with no items

#### Scenario: Concurrent catalog mutation makes the cursor stale
- **WHEN** a branch mutation increments the catalog generation after page one
- **THEN** the next-page call returns `branch_cursor_stale` rather than claiming a duplicate-free snapshot

### Requirement: Branch summaries are exact, minimal, and authority-neutral
The system SHALL return `BranchListResultV1` with only `schema_version="branch-list-v1"`, `items: BranchSummaryV1[]`, and optional `next_cursor`; it MUST NOT return a hidden total. `next_cursor` SHALL be omitted, not null, when no next page exists. Each `BranchSummaryV1` SHALL contain exactly: string `branch_def_id`; string `name`; string `description` truncated to at most 500 characters; boolean `description_truncated`; string `author`; string `domain_id` which may be empty; string `goal_id` which may be empty; `tags` as at most 32 strings; `publication_state` as `published|unpublished`; optional string `active_branch_version_id`; non-negative integer `node_count`; non-negative integer `ordinary_edge_count`; non-negative integer `conditional_edge_count`; non-negative integer `skill_count`; boolean `has_source_nodes`; boolean `structurally_valid`, defined only as `BranchDefinition.validate()` returning no errors; and an RFC 3339 UTC string `updated_at`. `active_branch_version_id` SHALL be omitted, not null, when absent. A `published`-scope item MUST have `publication_state="published"` and a version ID verified against the authoritative version store; `mine` MAY return `unpublished`.

A summary MUST NOT contain node bodies, prompt templates, source code, state values, wiki paths/titles/summaries/match counts, universe metadata, provider/custody/gate data, private host topology, or execution/purchase authority. `structurally_valid=true` MUST NOT be described as provider availability, source approval, sandbox readiness, compute authority, or execution readiness.

#### Scenario: Catalog projection excludes restricted wiki metadata
- **WHEN** an admitted branch has node text that matches a restricted wiki page
- **THEN** its summary contains no related-wiki field, path, title, summary, or match count

#### Scenario: Listing grants no execution authority
- **WHEN** a caller receives a public branch summary with `structurally_valid=true`
- **THEN** the result conveys no permission to run the branch, spend funds, select a provider, or purchase compute
- **AND** any later `run_graph` call applies its own authority, provider, and capacity gates

### Requirement: Catalog and exact inspection compose without restricted-page disclosure
The system SHALL keep both new `read_graph(target="branches")` and complete-definition create mode unavailable until canonical `read_graph(target="branch")`, internal/legacy `get_branch`, `describe_branch`, and their shared related-wiki helper enforce page and universe visibility before deriving related-wiki metadata. A caller who discovers or creates a branch ID MUST NOT learn any item, path, title, summary, boolean, match count, or existence evidence for a page withheld from that caller. If every exact path is not safe, catalog SHALL return `branch_catalog_unavailable`, create SHALL return `branch_create_unavailable`, and deployment/prompt/rendered acceptance of the new journey MUST remain blocked.

#### Scenario: Catalog-to-exact-read does not disclose a restricted page
- **WHEN** a caller discovers a public branch and then reads it exactly while one matching wiki page is withheld by page or universe visibility
- **THEN** the exact branch result contains no metadata or match-count evidence for the withheld page

#### Scenario: Unsafe exact projection disables catalog rollout
- **WHEN** the deployed exact branch projection still exposes restricted related-wiki metadata
- **THEN** new catalog and create modes are unavailable and final rendered inspection cannot be accepted

### Requirement: Branch write is a closed create-or-patch union
The system SHALL treat `write_graph(target="branch")` as a closed discriminated union over the existing handle parameters plus `definition_json`. Create mode SHALL require empty `branch_id` and `changes_json`, non-empty `definition_json`, a 16–128 character `idempotency_key`, and the existing top-level `visibility` parameter to remain exactly its default `"public"`. V1 hosted creation is commons-only; any other visibility SHALL return `branch_visibility_unsupported_v1` before persistence. Create mode SHALL require `name`, `description`, `tags`, `text`, `graph_id`, `pickup_incentive`, `directed_daemon_id`, and `directed_daemon_instruction` to be empty, `request_type` to remain `general`, and `priority_weight` to remain zero.

Patch mode SHALL require non-empty `branch_id` and `changes_json`, empty `definition_json` and `idempotency_key`, top-level `visibility="public"`, and every other non-mode parameter at the same default values. Patch mode SHALL preserve the existing all-operations-or-none staging behavior, but it SHALL NOT be described as idempotent or compare-and-swap because no expected version/hash is supplied. Mixed, incomplete, or irrelevant non-default input MUST return `branch_write_mode_invalid` before any branch handler, storage, ledger, or export operation runs.

#### Scenario: Complete definition selects create mode
- **WHEN** an authenticated caller supplies `definition_json` and `idempotency_key` with every irrelevant field and visibility at its default
- **THEN** the server validates and attempts exactly one durable branch creation

#### Scenario: Existing identifier selects patch mode
- **WHEN** an authorized caller supplies only `branch_id` and `changes_json` beyond target/default values
- **THEN** the server delegates to the existing transactional batch-patch path without claiming retry idempotency or CAS

#### Scenario: Mixed or irrelevant inputs fail before dispatch
- **WHEN** a caller mixes create and patch fields, supplies a patch idempotency key, duplicates visibility inside the definition, or sets an irrelevant non-default field
- **THEN** the server returns `branch_write_mode_invalid` before dispatch and changes no state

### Requirement: BranchCreateDefinitionV1 is a closed prompt-template starter schema
The system SHALL accept create input only as a JSON object with `schema_version="branch-definition-v1"`. Required top-level fields SHALL be `name`, `node_defs`, `edges`, `entry_point`, and `state_schema`; the only optional top-level fields SHALL be `description`, `domain_id`, `tags`, and `conditional_edges`. `visibility`, `goal_id`, `fork_from`, `skills`, `concurrency_budget`, `default_llm_policy`, IDs, authorship/provenance, approvals, publication state, timestamps, statistics, ownership/ACL, tenant/universe, custody/gate, and related-wiki fields MUST be rejected as structural keys. Goal binding, fork/remix, skills, code nodes, node references/copy intents, model/provider hints, and child-branch/version invocation require separate canonical reviewed contracts.

When optional top-level fields are omitted, `description` and `domain_id` SHALL default to empty strings and `tags` and `conditional_edges` SHALL default to empty arrays. These defaults SHALL be applied before RFC 8785 command-digest computation so omitted and explicitly supplied default values have one canonical command body.

Each `node_defs` item SHALL be an object requiring string `node_id`, string `display_name`, and string `prompt_template`; its only optional keys SHALL be string `description`, `phase` in `orient|plan|draft|commit|learn|reflect|enrich|custom`, string-array `input_keys`, string-array `output_keys`, boolean `strict_input_isolation`, and integer `timeout_seconds`. Node `source_code`, `node_ref`, dependencies, tools/effects, retry/checkpoint/evaluation policy, model/reasoning/provider policy, invoke/await specifications, author/registration, enablement, and approval fields MUST be rejected.

When optional node fields are omitted, `description=""`, `phase="custom"`, `input_keys=[]`, `output_keys=[]`, `strict_input_isolation=true`, and `timeout_seconds=300` SHALL apply before validation, persistence, and command-digest computation.

Each ordinary edge SHALL contain exactly string `from` and string `to`. Each conditional edge SHALL contain exactly string `from` and `conditions`, where `conditions` is an object of 1–64 unique outcome strings of 1–128 characters mapped to target-node identifiers. Each state field SHALL require string `name` and may contain only `type` in the existing compiler vocabulary `str|int|float|bool|list|dict|any`, `reducer` in `overwrite|append|merge`, JSON-compatible `default_value`, and string `description`. The boundary SHALL persist these values unchanged and SHALL mutation-test every vocabulary member against the graph compiler; it MUST NOT silently coerce an unknown type to `any`. A default value SHALL have maximum nesting depth 8, at most 1,024 aggregate array/object members, object keys of at most 128 characters, string leaves of at most 10,000 characters, and only finite JSON numbers. Protected-key rejection applies to these structural object scopes and SHALL NOT scan arbitrary prompt or description text for coincidental words.

When optional state-field keys are omitted, `type="any"`, `reducer="overwrite"`, and `description=""` SHALL apply; omitted `default_value` SHALL mean no seeded value and SHALL remain absent. Defaults SHALL be applied before validation, persistence, and command-digest computation.

The UTF-8 `definition_json` SHALL be at most 1,048,576 bytes; name SHALL be 1–200 characters; descriptions SHALL be at most 10,000 characters; display names SHALL be 1–200 characters; structural identifiers SHALL be 1–128 characters; tags SHALL contain at most 32 unique values of at most 64 characters each; node definitions SHALL contain 1–256 unique node IDs; ordinary plus conditional edges SHALL total at most 1,024; state schema SHALL contain at most 256 unique field names; input/output key arrays SHALL contain at most 64 unique identifiers; prompt templates SHALL be at most 200,000 characters; and node timeout SHALL be a finite integer in the inclusive range 1–600 seconds. Optional keys SHALL be omitted rather than encoded as `null` unless their declared type explicitly includes null; no V1 field does.

#### Scenario: Source-code and reference nodes are rejected in V1
- **WHEN** a definition supplies `source_code`, `node_ref`, copy intent, child-branch/version invocation, or approval fields
- **THEN** creation returns `branch_validation_failed` with bounded structural field paths
- **AND** no branch, idempotency success, outbox intent, or export is created

#### Scenario: Oversized definition is rejected before parsing work
- **WHEN** `definition_json` exceeds 1,048,576 UTF-8 bytes
- **THEN** creation returns `branch_validation_failed` without echoing the definition or invoking storage

#### Scenario: Structurally invalid graph is atomic
- **WHEN** the closed definition passes shape caps but fails `BranchDefinition.validate()`
- **THEN** the result contains bounded validation paths and no attempted prompt text
- **AND** no partial branch, idempotency success, outbox intent, or export exists

### Requirement: Verified authority owns new content without erasing provenance
The system SHALL derive the new branch owner and each new inline node author from the verified request principal and MUST NOT use caller fields, `UNIVERSE_SERVER_USER`, another environment fallback, graph membership, or branch name as positive authority. V1 SHALL NOT accept fork, copy, node-reference, or Goal-binding inputs. A future admitted remix MUST preserve immutable source attribution separately from current branch ownership rather than replacing inherited authors with the forking actor.

#### Scenario: Environment identity cannot create or claim a branch
- **WHEN** no verified request principal exists but an environment actor variable is set
- **THEN** creation returns `branch_authentication_required` and persists nothing

#### Scenario: New nodes inherit verified authorship
- **WHEN** an authenticated actor creates a V1 starter branch
- **THEN** the branch owner and every new inline node author are derived from that actor
- **AND** no caller-supplied authorship field is accepted

#### Scenario: Goal binding is not silently persisted
- **WHEN** a V1 definition supplies `goal_id`
- **THEN** creation returns `branch_validation_failed` rather than bypassing Goal existence, deletion, authority, mirror, or commit invariants

### Requirement: Existing patch mode cannot carry caller-authored authority
Every `write_graph(target="branch")` patch operation SHALL reject caller-supplied branch or node author/owner, approval, `approved_by`, `approved_source_hash`, registration, publication-authority, and generated identifier fields before staging. A newly added inline node SHALL derive its author from the verified request principal. A source-code add or source-code change, where the existing patch contract admits it, SHALL persist unapproved and SHALL require a separately reviewed canonical approval route before execution. The legacy source-approval action MUST NOT be retired until that route exists or source-code patching is removed through a separately reviewed migration.

#### Scenario: Self-approved node patch is rejected
- **WHEN** an authorized branch owner submits an add-node or edit-node patch containing `author`, `approved`, `approved_by`, or `approved_source_hash`
- **THEN** the patch returns `branch_validation_failed` and commits none of its operations

#### Scenario: Source mutation cannot preserve stale approval
- **WHEN** an authorized patch changes admitted source code without supplying protected fields
- **THEN** the node author is derived from verified authority and all approval state is cleared before persistence

### Requirement: Branch creation is body-bound idempotent with reconciled attribution
The system SHALL require the 16–128 character raw idempotency key to use printable ASCII bytes `0x21`–`0x7e`. For each retained versioned server secret it SHALL compute `HMAC-SHA256(secret, "branch-create-key-v1\0" || RFC8785([verified_actor_subject, raw_key]))`, probe every retained-version fingerprint, and reserve unique alias rows for every retained fingerprint in the same write transaction before designating the current-version fingerprint. The overlapping alias set SHALL prevent rolling servers on adjacent key versions from reserving the same actor/raw-key command twice. It MUST NOT store or log the raw key. The command digest SHALL be SHA-256 over RFC 8785 canonical JSON containing the accepted V1 definition, top-level visibility, verified actor subject, and schema version. Active and prior verification keys SHALL remain available for at least the idempotency retention window.

The canonical branch row, catalog projection/generation, succeeded idempotency result and aliases, and branch-creation outbox record with a stable random `event_id` SHALL commit in one canonical database transaction. The storage API SHALL provide one connection-accepting transaction seam rather than nesting the current branch save's independent connection. Same-actor same-key same-digest replay SHALL return the original `BranchCreateResultV1`; changed-digest reuse MUST return `branch_idempotency_conflict`. Succeeded records and aliases SHALL be retained for at least 24 hours; the configured retention SHALL be disclosed in operator configuration. After expiry, reuse MAY create a new branch and MUST NOT be reported as replay of the expired command. A crash before commit SHALL leave none of those rows and allow retry; a crash after commit but before response SHALL replay the original result while the pending outbox remains. The outbox record itself is V1's concrete durable attribution record; V1 requires no second ledger or projection table. Delivery to optional future consumers MAY be at least once, but any such consumer MUST deduplicate by `event_id`. Source-control/GitHub export SHALL be downstream and MUST NOT be claimed as atomic with create success.

#### Scenario: Identical retry returns the original branch
- **WHEN** the same actor repeats a successful create with the same raw key and canonical body
- **THEN** the server returns the original `branch_def_id` and no second branch or outbox intent

#### Scenario: Changed body conflicts
- **WHEN** the same actor reuses a key with any changed canonical definition or top-level visibility
- **THEN** the server returns `branch_idempotency_conflict` and preserves the original result

#### Scenario: Concurrent retries have one durable branch result
- **WHEN** 100 concurrent calls submit the same actor, key, and canonical body
- **THEN** every successful reply identifies one branch and durable state contains one branch, one idempotency result, and one attribution-outbox intent

#### Scenario: Downstream export failure does not duplicate attribution
- **WHEN** branch creation commits and an optional outbox consumer or export fails
- **THEN** create replay returns the original branch result and the same stable `event_id` remains available without creating another branch or outbox record

### Requirement: Create results and errors are closed and non-secret
The system SHALL return successful creation as `BranchCreateResultV1` containing exactly `schema_version="branch-create-result-v1"`, `status="created"`, `branch_def_id`, `name`, `publication_state="unpublished"`, `validation_status="structurally_valid"`, `node_count`, `ordinary_edge_count`, `conditional_edge_count`, and optional opaque `receipt_id`. `validation_status` MUST NOT imply provider availability, source approval, sandbox readiness, compute authority, or execution readiness.

Branch errors SHALL contain exactly `schema_version="branch-error-v1"`, stable `error` code, human message of at most 500 characters, and optional `field_paths` containing at most 20 paths of at most 256 characters each. Supported codes MUST include `branch_read_mode_invalid`, `branch_write_mode_invalid`, `branch_validation_failed`, `branch_authentication_required`, `branch_not_found`, `branch_cursor_invalid`, `branch_cursor_stale`, `branch_idempotency_conflict`, `branch_visibility_unsupported_v1`, `branch_catalog_unavailable`, `branch_create_unavailable`, and `branch_write_failed`. Optional `field_paths` SHALL be omitted rather than null. Results and errors MUST NOT expose the attempted definition, prompt text, SQL, filesystem paths, stack traces, restricted metadata, or evidence that an unauthorized object exists.

#### Scenario: Successful create returns a minimal structural result
- **WHEN** a public branch create succeeds
- **THEN** the result returns the generated branch ID, exact counts, unpublished state, and structural validation status only
- **AND** it does not claim that a provider, model, compute host, budget, or approval is available

#### Scenario: Validation error is bounded
- **WHEN** more than 20 fields fail validation
- **THEN** the error returns at most 20 bounded field paths and does not echo `definition_json`

### Requirement: V1 creation is commons-only
Hosted `BranchCreateDefinitionV1` SHALL create only public-commons records. It MUST NOT create a platform private row, `is_private` substitute, private metadata projection, or proxy into an unspecified private store. Private authoring requires a later PLAN-approved user-controlled storage and routing contract.

#### Scenario: Private visibility is outside V1
- **WHEN** an authenticated hosted-MCP caller requests top-level `visibility="private"`
- **THEN** the call returns `branch_visibility_unsupported_v1` before branch, idempotency-success, outbox, projection, or export persistence

#### Scenario: Commons creation uses no maintainer quota
- **WHEN** the same authenticated caller creates a valid commons branch
- **THEN** creation can proceed without maintainer compute or provider quota and grants no later execution authority

### Requirement: First-contact branch path has concurrent-client proof
The system SHALL provide a deterministic declared-environment load fixture with 500 logical clients and 1,000 mixed operations: 800 catalog reads and 200 create attempts, including tied timestamps, 100 concurrent same-key retries, unsupported-private probes, catalog-generation invalidation, authoritative-publication verification, and cross-actor cursor replay. The fixture SHALL use the production SQLite journaling and busy-timeout configuration on declared hardware. The proof MUST show zero 5xx responses, restricted metadata leaks, duplicate or partial branch results, silent pagination duplicates/skips, and advertised-handle drift, with p99 below three seconds in the declared environment.

#### Scenario: Mixed first-contact load stays correct
- **WHEN** the 500-client, 1,000-operation fixture runs against the reviewed server build
- **THEN** every correctness, privacy, idempotency, cursor, exact-seven, and p99-under-three-seconds assertion passes
