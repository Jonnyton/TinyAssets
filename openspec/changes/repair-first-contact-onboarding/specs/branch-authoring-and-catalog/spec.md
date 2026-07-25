## ADDED Requirements

### Requirement: Branch catalog is bounded, stable, and non-enumerating
The system SHALL expose branch discovery through `read_graph(target="branches")` using a closed `BranchListRequestV1` with `scope`, `query`, `tags`, `domain_id`, `goal_id`, `cursor`, and `limit`. `scope` SHALL be exactly `published` or `mine`, defaulting to `published`; `mine` SHALL require a verified authenticated actor. `published` SHALL admit only public branches with an active published version, while `mine` SHALL admit only branches authored by that verified actor and available through the canonical storage boundary. Authorization SHALL run before filtering, ordering, cursor evaluation, or projection. There SHALL be no public `all`, `visible`, `include_private`, hidden-total, or universe-membership shortcut.

The catalog SHALL use stable keyset order `(updated_at DESC, branch_def_id ASC)`, default `limit=25`, maximum `limit=100`, and an opaque `next_cursor` bound to the verified actor, scope, and normalized filters. `BranchListResultV1` SHALL contain only `schema_version="branch-list-v1"`, `items`, and optional `next_cursor`.

#### Scenario: Anonymous default lists only active published public branches
- **WHEN** an anonymous caller invokes `read_graph(target="branches")` without a scope
- **THEN** the result contains at most 25 public branches with active published versions
- **AND** no private, unpublished, or caller-owned-only row is admitted

#### Scenario: Mine requires verified identity
- **WHEN** an anonymous caller requests `scope="mine"`
- **THEN** the call returns `branch_authentication_required` with no branch items

#### Scenario: Foreign private branch is not enumerable
- **WHEN** actor A pages or filters the catalog while actor B owns a private branch matching every supplied filter
- **THEN** actor B's branch contributes no item, total, cursor behavior, match count, or other existence evidence

#### Scenario: Tied updates paginate without duplicates or skips
- **WHEN** more than one admitted branch has the same `updated_at` and the caller follows `next_cursor`
- **THEN** `(updated_at DESC, branch_def_id ASC)` produces each admitted branch exactly once

#### Scenario: Cursor cannot cross actors or filters
- **WHEN** a cursor is altered or replayed under a different actor, scope, or normalized filter set
- **THEN** the call returns `branch_cursor_invalid` with no items

### Requirement: Branch summaries are minimal and authority-neutral
The system SHALL return each `BranchSummaryV1` with only `branch_def_id`, `name`, a bounded `description`, `author`, `domain_id`, `goal_id`, bounded `tags`, `visibility`, publication state, optional active `branch_version_id`, `node_count`, `edge_count`, `skill_count`, `has_sandbox_nodes`, and `updated_at`. A summary MUST NOT contain node bodies, prompt templates, source code, state values, wiki paths/titles/summaries/match counts, universe metadata, provider/custody/gate data, private host topology, or execution/purchase authority.

#### Scenario: Catalog projection excludes restricted wiki metadata
- **WHEN** an admitted branch has node text that matches a restricted wiki page
- **THEN** its summary contains no related-wiki field, path, title, summary, or match count

#### Scenario: Listing grants no execution authority
- **WHEN** a caller receives a public branch summary
- **THEN** the result conveys no permission to run the branch, spend funds, select a provider, or purchase compute
- **AND** any later `run_graph` call applies its own authority and capacity gates

### Requirement: Branch write is a closed create-or-patch union
The system SHALL treat `write_graph(target="branch")` as a closed discriminated union. Create mode SHALL require empty `branch_id`, empty `changes_json`, non-empty `definition_json`, and a valid `idempotency_key`. Patch mode SHALL require non-empty `branch_id` and non-empty `changes_json` and SHALL forbid `definition_json`. Mixed or incomplete input MUST return `branch_write_mode_invalid` before any branch handler, storage, ledger, or commit operation runs. Existing transactional patch behavior SHALL remain otherwise unchanged.

#### Scenario: Complete definition selects create mode
- **WHEN** an authenticated caller supplies `definition_json` and `idempotency_key` with no `branch_id` or `changes_json`
- **THEN** the server validates and attempts exactly one atomic branch creation

#### Scenario: Existing identifier selects patch mode
- **WHEN** an authorized caller supplies `branch_id` and `changes_json` with no `definition_json`
- **THEN** the server delegates to the existing transactional patch path

#### Scenario: Mixed create and patch inputs fail closed
- **WHEN** a caller supplies `definition_json` together with `branch_id` or `changes_json`
- **THEN** the server returns `branch_write_mode_invalid` before dispatch and changes no state

### Requirement: BranchCreateDefinitionV1 is closed and bounded
The system SHALL accept create input only as a JSON object with `schema_version="branch-definition-v1"`. Required fields SHALL be `name`, `node_defs`, `edges`, `entry_point`, and `state_schema`; the closed optional set SHALL be `description`, `domain_id`, `tags`, `conditional_edges`, `skills`, `fork_from`, `goal_id`, `visibility`, `default_llm_policy`, and `concurrency_budget`. Unknown top-level fields MUST be rejected.

The UTF-8 `definition_json` SHALL be at most 1,048,576 bytes; name SHALL be 1–200 characters; description SHALL be at most 10,000 characters; identifiers SHALL be at most 128 characters; tags SHALL contain at most 32 values of at most 64 characters each; node definitions SHALL contain at most 256 nodes; ordinary plus conditional edges SHALL total at most 1,024; state schema SHALL contain at most 256 fields; skills SHALL contain at most 64 snapshots; and any single prompt, source, or skill-body string SHALL be at most 200,000 characters while remaining under the total body cap.

Branch/version IDs, branch or node authors, registration fields, approval fields, publication state, timestamps, statistics, ownership/ACL, tenant/universe, custody/gate, and related-wiki fields SHALL be server-owned and MUST be rejected if supplied anywhere in the create definition.

#### Scenario: Caller-supplied ownership and approval fields are rejected
- **WHEN** a definition supplies a branch author, node author, approval, ID, timestamp, ownership, tenant, or publication field
- **THEN** creation returns `branch_validation_failed` naming only bounded field paths
- **AND** no branch, ledger row, idempotency success, or commit is created

#### Scenario: Oversized definition is rejected before parsing work
- **WHEN** `definition_json` exceeds 1,048,576 UTF-8 bytes
- **THEN** creation returns `branch_validation_failed` without echoing the definition or invoking storage

#### Scenario: Structurally invalid graph is atomic
- **WHEN** the closed definition passes shape caps but fails `BranchDefinition.validate()`
- **THEN** the result contains bounded validation paths and no attempted prompt/source text
- **AND** no partial branch, ledger row, idempotency success, or commit exists

### Requirement: Verified authority owns authorship and fork visibility
The system SHALL derive branch and node authorship from the verified request principal and MUST NOT use caller fields, `UNIVERSE_SERVER_USER`, another environment fallback, graph membership, or branch name as positive authority. `fork_from` SHALL resolve only an active published public branch version or a private version owned by the same verified actor and reachable through eligible user-controlled storage. Missing and unauthorized fork sources MUST return the identical `branch_not_found` envelope before lineage or content is disclosed.

#### Scenario: Environment identity cannot create or claim a branch
- **WHEN** no verified request principal exists but an environment actor variable is set
- **THEN** creation returns `branch_authentication_required` and persists nothing

#### Scenario: Foreign private fork is indistinguishable from missing
- **WHEN** an authenticated caller supplies either a nonexistent `fork_from` or another actor's private version
- **THEN** both calls return the same `branch_not_found` shape and reveal no lineage metadata

#### Scenario: Public remix records safe lineage
- **WHEN** an authenticated caller creates from an active published public version
- **THEN** the new branch records that visible version lineage while deriving all ownership fields from the caller

### Requirement: Branch creation is actor-scoped and body-bound idempotent
The system SHALL require a 16–128 character create `idempotency_key` and SHALL reserve it transactionally under the verified actor with a canonical digest of the accepted V1 definition plus effective visibility and lineage. Same-actor same-key same-body replay SHALL return the original `BranchCreateResultV1`; changed-body reuse MUST return `branch_idempotency_conflict`. Concurrent identical calls SHALL produce exactly one branch, one attribution/ledger record, and one storage commit.

#### Scenario: Identical retry returns the original branch
- **WHEN** the same actor repeats a successful create with the same key and canonical body
- **THEN** the server returns the original `branch_def_id` and no second branch, ledger record, or commit

#### Scenario: Changed body conflicts
- **WHEN** the same actor reuses a key with any changed canonical definition, visibility, or lineage field
- **THEN** the server returns `branch_idempotency_conflict` and preserves the original result

#### Scenario: Concurrent retries have one winner
- **WHEN** 100 concurrent calls submit the same actor, key, and canonical body
- **THEN** all successful replies identify one branch and durable state contains one branch, one ledger record, and one commit

### Requirement: Create results and errors are closed and non-secret
The system SHALL return successful creation as `BranchCreateResultV1` containing only `schema_version="branch-create-result-v1"`, `status="created"`, `branch_def_id`, `name`, `visibility`, `published=false`, `runnable`, `node_count`, `edge_count`, and optional opaque `receipt_id`. Branch errors SHALL use `schema_version="branch-error-v1"`, a stable `error` code, bounded human message, and optional bounded field paths. Supported codes MUST include `branch_write_mode_invalid`, `branch_validation_failed`, `branch_authentication_required`, `branch_not_found`, `branch_cursor_invalid`, `branch_idempotency_conflict`, `branch_private_storage_unavailable`, and `branch_write_failed`.

Neither results nor errors SHALL expose the attempted definition, prompt/source text, SQL, filesystem paths, stack traces, restricted metadata, or evidence that an unauthorized object exists.

#### Scenario: Successful create round-trips by generated ID
- **WHEN** a public branch create succeeds
- **THEN** the minimal result returns a generated `branch_def_id`
- **AND** an authorized exact `read_graph(target="branch", branch_id=<id>)` can inspect that branch under its independent projection rules

#### Scenario: Validation error is bounded
- **WHEN** several fields fail validation
- **THEN** the error lists only bounded field paths and stable codes and does not echo `definition_json`

### Requirement: Private creation requires user-controlled storage
The system SHALL persist public branches to the platform commons and SHALL persist private branch content only through an eligible user-controlled host/storage route. Hosted MCP private creation without such a route MUST return `branch_private_storage_unavailable` before branch, metadata, ledger, idempotency-success, or commit persistence.

#### Scenario: Hosted private create has no eligible host
- **WHEN** an authenticated hosted-MCP caller requests `visibility="private"` and no eligible user-controlled storage route is available
- **THEN** the call returns `branch_private_storage_unavailable` and the platform stores no private branch content or metadata row

#### Scenario: Public commons creation remains independent
- **WHEN** the same authenticated caller creates a valid public branch
- **THEN** public creation can proceed without maintainer compute, provider quota, or a private-storage decision

### Requirement: First-contact branch path has concurrent-client proof
The system SHALL provide a deterministic declared-environment load fixture with 500 logical clients and 1,000 mixed branch-catalog/create operations, including tied timestamps, 100 concurrent same-key retries, foreign-private probes, and cross-actor cursor replay. The proof MUST show zero 5xx responses, restricted metadata leaks, duplicate or partial creates, pagination duplicates/skips, and advertised-handle drift, with p99 below three seconds in that declared environment.

#### Scenario: Mixed first-contact load stays correct
- **WHEN** the 500-client, 1,000-operation fixture runs against the reviewed server build
- **THEN** every correctness, privacy, idempotency, pagination, exact-seven, and declared-latency assertion passes
