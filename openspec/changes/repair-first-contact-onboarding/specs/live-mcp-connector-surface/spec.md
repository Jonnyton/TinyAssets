## ADDED Requirements

### Requirement: First-contact branch onboarding composes through the canonical handles
The live MCP connector SHALL support bounded branch discovery through `read_graph(target="branches")` and the closed create-patch-publish modes of `write_graph(target="branch")` without requiring a hidden, retired, compatibility, or additional tool. The new catalog and complete-definition create/publish modes plus their prompt guidance MUST remain unavailable in deployed and rendered surfaces until canonical `read_graph(target="branch")`, internal/legacy `get_branch`, `describe_branch`, and their shared related-wiki helper have visibility-safe exact projections that cannot disclose any item, path, title, summary, boolean, count, or existence evidence for a restricted page.

#### Scenario: Branch discovery needs no opaque identifier
- **WHEN** a newly connected client calls `read_graph(target="branches")`
- **THEN** it receives the bounded branch catalog contract without first supplying a branch or graph ID

#### Scenario: Complete branch creation stays under write_graph
- **WHEN** an authenticated client supplies a valid branch definition through `write_graph(target="branch")`
- **THEN** the request uses the canonical write handle and no `extensions` or standalone build tool is required

#### Scenario: Deliberate publication stays under write_graph
- **WHEN** an authorized author publishes a validated branch through `write_graph(target="branch", publish=true)`
- **THEN** the canonical handle mints one catalog-published version without a hidden `publish_version` action

#### Scenario: Unsafe exact inspection blocks catalog rollout
- **WHEN** exact branch inspection can still reveal metadata for a restricted wiki page
- **THEN** the catalog target returns `branch_catalog_unavailable`, create returns `branch_create_unavailable`, and publish returns `branch_publish_unavailable`
- **AND** its first-contact prompt guidance, deployment acceptance, and rendered journey remain blocked

### Requirement: Registered onboarding prompts teach only canonical current behavior
The registered `control_station`, `meet_universe`, `extension_guide`, and `branch_design_guide` prompts SHALL describe executable user journeys only through the canonical handles and supported targets. They MUST NOT instruct a chatbot to call `universe`, `community_change_context`, `extensions`, `goals`, `gates`, `wiki`, `/mcp-directory*`, or another hidden/retired tool or route. First contact SHALL begin through `converse`. First-contact branch authoring SHALL use the prompt-template-only V1 catalog/create/inspect/publish composition and MUST NOT teach source-code authoring, approval, fork/remix, Goal binding, or other excluded V1 shapes. Before any `run_graph` step, the guidance SHALL state that the requester must attach or authorize their own BYOC/market provider and that TinyAssets never uses maintainer/founder provider quota for the run. Any broader source-code guidance SHALL disclose that the current compiled path is not OS-isolated and SHALL NOT claim a canonical approval route until one exists.

#### Scenario: Prompt catalog contains no retired invocation
- **WHEN** all four registered prompt bodies and docstrings are inspected
- **THEN** no example or instruction invokes a hidden/retired tool or route

#### Scenario: Meet-universe guide begins with converse
- **WHEN** a newly connected chatbot loads `meet_universe`
- **THEN** the guide directs the user's actual opening message through `converse`
- **AND** it does not tell the chatbot to provision through `get_status`

#### Scenario: Branch guide is executable through advertised handles
- **WHEN** a chatbot follows `branch_design_guide` for a prompt-template-only V1 branch from discovery through create, inspect, publish, and optional run
- **THEN** every step maps to `read_graph`, `write_graph`, or `run_graph` with a supported target and parameter shape

#### Scenario: Run guidance never spends maintainer quota
- **WHEN** the starter guide reaches an optional run step without requester-owned provider authority
- **THEN** it tells the user how to attach or authorize their own BYOC/market provider
- **AND** it does not invoke a maintainer, founder, or ambient fallback provider

#### Scenario: Extension guide does not overclaim sandbox isolation
- **WHEN** a chatbot loads `extension_guide`
- **THEN** the guide states the current source-code isolation limitation and does not claim OS sandboxing that the compiled path lacks

### Requirement: Repository guidance and live wiki corrections have separate proof
The system SHALL maintain an exact-path, lower-bound planning manifest for known first-contact repository prompts and live wiki pages that teach retired tools or an opaque-ID-only branch flow. It SHALL NOT call that inventory exhaustive until a privileged `scope=all` inventory or volume export has been reconciled. Each live wiki entry MUST record its exact path, audience, pre-image SHA-256, exact replacement, dry-run result, guarded-write result, and post-image SHA-256. The existing `expected_sha256` check is a race-prone stale-write precondition, not atomic compare-and-swap. No live correction SHALL run until a separately reviewed serialized/locked single-writer boundary makes the precondition and mutation atomic. A repository change SHALL NOT be reported as a live wiki change, and a live wiki change SHALL NOT be made through path guessing, router heuristics, or an unguarded overwrite.

#### Scenario: Repository prompt correction does not imply live wiki mutation
- **WHEN** source-owned prompt text changes but no serialized guarded live-wiki write has succeeded
- **THEN** the manifest reports the source correction separately and the live page remains pending

#### Scenario: Stale live page conflicts instead of overwriting
- **WHEN** the serialized writer observes that a live page's current hash differs from the refreshed manifest pre-image
- **THEN** the guarded write returns a conflict and no page content is overwritten

### Requirement: Legacy branch-tool retirement is replacement-first
Any retirement of a hidden branch catalog/build/publication/approval action SHALL wait until its canonical equivalent is deployed where required, registered prompt consumers are migrated, and the affected rendered chatbot journey has passed. The legacy `publish_version` action MUST remain available to its existing authorized callers until canonical publish mode is deployed and its migration proof passes. The legacy source-code approval action MUST remain available until a canonical approval route exists or source-code patching has been separately removed. When this delta and the legacy-retirement delta are implemented, their concurrent modifications to `Canonical Advertised Handle Set` SHALL be reconciled and synchronized together without dropping either change's surviving requirements.

#### Scenario: Retirement cannot strand branch authors
- **WHEN** canonical prompt-template catalog/create/publish is ready but source-code patch approval has no canonical route
- **THEN** prompt-template onboarding may proceed
- **AND** retirement of the legacy approval action remains blocked

### Requirement: Rendered chatbot acceptance proves the complete first-contact branch journey
Final public acceptance SHALL use a real browser-rendered chatbot with the installed `TinyAssets` connector at `https://tinyassets.io/mcp`. The conversation MUST discover a published branch without a prior branch ID, create one complete public prompt-template V1 branch, inspect the returned ID through the visibility-safe exact projection, publish it deliberately, rediscover it through the catalog, and observe the canonical exact tool surface required by the base specification. If the acceptance journey runs the branch, it MUST use requester-owned BYOC/market authority and prove no maintainer/founder quota was selected. Direct MCP calls, local tests, DOM-only checks, and canaries SHALL remain supporting evidence rather than final user-surface proof.

#### Scenario: Real chatbot completes branch onboarding
- **WHEN** a user-like tester asks the connected chatbot to browse examples and create a small workflow branch
- **THEN** the rendered conversation completes discovery, creation, inspection, publication, and rediscovery through canonical handles
- **AND** the prompt/result plus trace or screenshot evidence is saved in `output/user_sim_session.md`

#### Scenario: Organic-use proof is absent
- **WHEN** no post-fix real-user evidence is visible after deployment
- **THEN** the result states that explicitly and leaves a concise STATUS monitoring item instead of claiming proven clean use

## MODIFIED Requirements

### Requirement: Canonical Advertised Handle Set

The advertised `tools/list` surface SHALL be exactly seven handles: `read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, and `get_status`. Each SHALL remain a thin shape/target router over shared `tinyassets.api.*` owners; target-specific closed validation, verified-authority derivation, and hardening SHALL live at the shared handler/staging boundary so every canonical, internal, or temporarily retained legacy alias inherits the same security invariant. The public drift-guard canary (`scripts/mcp_public_canary.py --assert-handles`) SHALL require that exact set; a missing `get_status` or any extra advertised handle is drift.

#### Scenario: Live surface advertises exactly the seven handles

- **WHEN** a client reads `tools/list` from the running server with middleware applied
- **THEN** the advertised set equals `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}` and nothing else
- **AND** `converse` is present as a user-facing handle

#### Scenario: A canonical handle routes through the shared hardened owner

- **WHEN** a client calls a canonical branch target that shares staging or projection with an internal/legacy alias
- **THEN** both paths apply the same protected-field, verified-authority, visibility, and bounded-result invariants

#### Scenario: A canonical handle routes to its existing API owner

- **WHEN** a client calls `write_graph(target="goal", ...)` and later `read_graph(target="goals", ...)`
- **THEN** the write routes to the same goals owner the read queries, so the proposed goal is returned by the read

#### Scenario: An unknown router target is reported, not silently accepted

- **WHEN** a client calls `read_graph(target="bogus")`
- **THEN** the result is a JSON error with `error="unknown_target"`, `handle="read_graph"`, and the list of allowed targets
