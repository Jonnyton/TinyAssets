## ADDED Requirements

### Requirement: Canonical handles provide complete first-contact branch onboarding
The live MCP connector SHALL keep the advertised tool set exactly `{read_graph, write_graph, run_graph, read_page, write_page, converse, get_status}` while supporting `read_graph(target="branches")` for bounded discovery and the closed create-or-patch modes of `write_graph(target="branch")`. It MUST NOT register, advertise, alias, or recommend an eighth branch tool or any retired fat tool to complete this journey.

#### Scenario: Branch discovery needs no opaque identifier
- **WHEN** a newly connected client calls `read_graph(target="branches")`
- **THEN** it receives the bounded branch catalog contract without first supplying a branch or graph ID

#### Scenario: Complete branch creation stays under write_graph
- **WHEN** an authenticated client supplies a valid branch definition through `write_graph(target="branch")`
- **THEN** the request uses the canonical write handle and no `extensions` or standalone build tool is required

#### Scenario: Tool enumeration remains exactly seven
- **WHEN** the onboarding routes are present and a client lists tools
- **THEN** the advertised and registered canonical surface remains exactly the seven handles

### Requirement: Registered onboarding prompts teach only canonical current behavior
The registered `control_station`, `meet_universe`, `extension_guide`, and `branch_design_guide` prompts SHALL describe executable user journeys only through the seven canonical handles and supported targets. They MUST NOT instruct a chatbot to call `universe`, `community_change_context`, `extensions`, `goals`, `gates`, `wiki`, `/mcp-directory*`, or another hidden/retired tool or route. First contact SHALL begin through `converse`, branch authoring SHALL use the canonical branch catalog/create/patch/run composition, and source-code guidance SHALL disclose that the current compiled path is not OS-isolated.

#### Scenario: Prompt catalog contains no retired invocation
- **WHEN** all four registered prompt bodies and docstrings are inspected
- **THEN** no example or instruction invokes a hidden/retired tool or route

#### Scenario: Meet-universe guide begins with converse
- **WHEN** a newly connected chatbot loads `meet_universe`
- **THEN** the guide directs the user's actual opening message through `converse`
- **AND** it does not tell the chatbot to provision through `get_status`

#### Scenario: Branch guide is executable through advertised handles
- **WHEN** a chatbot follows `branch_design_guide` from discovery through create, inspect, and run
- **THEN** every step maps to `read_graph`, `write_graph`, or `run_graph` with a supported target and parameter shape

#### Scenario: Extension guide does not overclaim sandbox isolation
- **WHEN** a chatbot loads `extension_guide`
- **THEN** the guide states the current source-code isolation limitation and does not claim OS sandboxing that the compiled path lacks

### Requirement: Repository guidance and live wiki corrections have separate proof
The system SHALL maintain an exact correction manifest for every first-contact repository prompt and live wiki page that teaches retired tools or an opaque-ID-only branch flow. Each live wiki entry MUST record its exact path, audience, pre-image SHA-256, exact replacement, dry-run result, compare-and-swap result, and post-image SHA-256. A repository change SHALL NOT be reported as a live wiki change, and a live wiki change SHALL NOT be made through path guessing, router heuristics, or an unguarded overwrite.

#### Scenario: Repository prompt correction does not imply live wiki mutation
- **WHEN** source-owned prompt text changes but no live wiki compare-and-swap has succeeded
- **THEN** the manifest reports the source correction separately and the live page remains pending

#### Scenario: Stale live page conflicts instead of overwriting
- **WHEN** a live page's current hash differs from the manifest pre-image
- **THEN** the compare-and-swap returns a conflict and no page content is overwritten

### Requirement: Rendered chatbot acceptance proves the complete first-contact branch journey
Final public acceptance SHALL use a real browser-rendered chatbot with the installed `TinyAssets` connector at `https://tinyassets.io/mcp`. The conversation MUST discover a published branch without a prior branch ID, create one complete public branch, inspect the returned ID, and observe the exact seven-tool surface. Direct MCP calls, local tests, DOM-only checks, and canaries SHALL remain supporting evidence rather than final user-surface proof.

#### Scenario: Real chatbot completes branch onboarding
- **WHEN** a user-like tester asks the connected chatbot to browse examples and create a small workflow branch
- **THEN** the rendered conversation completes discovery, creation, and inspection through canonical handles
- **AND** the prompt/result plus trace or screenshot evidence is saved in `output/user_sim_session.md`

#### Scenario: Organic-use proof is absent
- **WHEN** no post-fix real-user evidence is visible after deployment
- **THEN** the result states that explicitly and leaves a concise STATUS monitoring item instead of claiming proven clean use
