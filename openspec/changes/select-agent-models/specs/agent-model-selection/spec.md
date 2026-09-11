## ADDED Requirements

### Requirement: Main and work-scoped choices are independent
The platform SHALL support owner-authorized main-agent provider/model changes
and independent provider/model choices for an agent, workflow or task. A work
choice SHALL NOT require changing the universe's main serving provider or
rewriting a private workflow. Preferences alone SHALL NOT grant execution access.

#### Scenario: Accepted model access followed by an ordinary workflow
- **WHEN** an owner successfully binds and enables accepted model access
- **THEN** a permitted foreground or background workflow can execute with no explicit pin
- **AND** the runtime validates the chosen member/model rather than treating the assignment as legacy authority

#### Scenario: A task chooses a different authorized source
- **WHEN** a task selects a supported provider/model within current accepted authority that differs from the main agent
- **THEN** its invocation uses that exact choice without changing the main agent or the task definition
- **AND** actual execution identity and settlement identify the source that ran

#### Scenario: Enabling model access preserves background polling
- **WHEN** a universe successfully enables accepted model access with an eligible source
- **THEN** it remains visible to the generic background coordinator for its authorized work
- **AND** inventory does not silently drop it through legacy single-provider validation
- **AND** actual launches still independently validate current authority and lifecycle

#### Scenario: Multiple sources share one work allowance
- **WHEN** different nodes or fallback attempts use different accepted sources
- **THEN** they remain constrained by the same work-level aggregate allowance and current per-source constraints
- **AND** concurrent attempts cannot multiply the budget or replay completed effects

#### Scenario: Main-provider change through ordinary controls
- **WHEN** the authorized user requests a main-provider change through the app agent
- **THEN** existing scoped operations and necessary owner confirmation perform and report the actual change
- **AND** no developer-console action or generic approval acknowledgement is presented as an executed repair

#### Scenario: A selected source cannot currently execute
- **WHEN** the choice is outside model/cost authority, revoked, stale or unsupported by its executor
- **THEN** execution refuses with the actual category before provider launch
- **AND** it neither silently changes the pin nor requests unrelated authentication as the repair

### Requirement: Connection-authored discovery contracts
The existing provider-capability action SHALL allow a versioned bounded data
contract for an unfamiliar connected model source, without provider-specific
platform callbacks or model-release lists. The exact contract, endpoint and
authority context SHALL be revalidated before model admission. Legacy descriptors
SHALL keep their prior interpretation and serialization.

#### Scenario: Owner configures a custom source contract
- **WHEN** an authorized owner configures a validated contract with optional preview
- **THEN** its successfully fetched catalogue may enter selection under existing accepted model, grant, executor and cost limits
- **AND** the UI distinguishes owner-configured source semantics from verified account availability
- **AND** configuration creates no inference or spending permission and cannot satisfy an independently required privacy restriction

#### Scenario: Catalogue invents trust or execution support
- **WHEN** remote data claims filtered availability, account identity, unmetered pricing or executor support
- **THEN** those claims cannot create trusted authority or an installed executor
- **AND** absent authenticated source configuration leaves the source unverified

#### Scenario: Unsupported charging or changed contract
- **WHEN** unknown charges, unenforceable ceilings, stale evidence or a changed contract invalidate a candidate
- **THEN** no inference uses the stale candidate and free-only routing cannot become paid

#### Scenario: Contract edits do not manufacture independent capacity
- **WHEN** separate custom-source connections lack independent account evidence
- **THEN** they share a conservative server-derived capacity scope
- **AND** changing a descriptor, host, key or model name cannot establish independent capacity

#### Scenario: Distinct unfamiliar catalogue shape
- **WHEN** a supported custom contract describes a new source schema and model ID
- **THEN** the existing picker and authorized agent route consume the normalized result without a platform edit
- **AND** unsupported wire protocols remain explicitly unsupported rather than fabricated success

### Requirement: Model access uses the existing owner binding action
The authenticated custom_agents bind_serving_provider action SHALL accept optional
model_access via strict ModelAccess validation and existing assignment publication.
Omission SHALL preserve the legacy provider-only payload. Saving preferences SHALL
NOT publish or widen assignments, grants or permitted spending.

#### Scenario: Owner opts into discovered models
- **WHEN** the owner binds authorized sources with discovered scope and accepted price limits
- **THEN** the current assignment records membership through existing authority
- **AND** broader discovery grants or paid allowances require explicit authorization

#### Scenario: Onboarding without opt-in
- **WHEN** the deposit flow has no explicit model-access declaration
- **THEN** it preserves legacy binding and working native serving behavior

#### Scenario: Mixed-source automatic mode
- **WHEN** a native default and HTTP models are eligible
- **THEN** automatic selection uses the native default through its real executor
- **AND** an HTTP-only catalog cannot silently remove that preference

#### Scenario: Saved automatic preference on an existing legacy binding
- **WHEN** an owner saves automatic mode and has a legacy provider-only assignment
- **THEN** a turn without a current override retains that provider's own default
- **AND** the saved policy and generation remain unchanged without granting model access
- **AND** current overrides or explicit saved choices still require accepted model authority

#### Scenario: Serving readiness reports its selected provider
- **WHEN** a manifest-backed agent is enabled successfully
- **THEN** the response provider identifies the plan's first eligible candidate
- **AND** the assignment anchor is not rewritten to impersonate the selected candidate

#### Scenario: Legacy readiness cannot execute the saved choice
- **WHEN** the current owned home has an explicit saved choice but no accepted model assignment
- **THEN** enabling serving refuses without modifying its binding or saved preference
- **AND** absent or saved automatic preferences preserve legacy provider-default readiness

#### Scenario: Many inactive agents do not hide serving authority
- **WHEN** more than100 newer inactive bindings exist in the universe
- **THEN** serving selection still considers every exact owner-serving match
- **AND** zero or multiple matches cannot be mistaken for one current binding

#### Scenario: Another owned universe retains legacy execution
- **WHEN** the owner converses with a non-home universe without an override
- **THEN** home-only preferences neither block nor alter its existing binding

### Requirement: Connection-scoped model choices
The app SHALL expose model choices from the universe owner's authorized connections with freshness and capability information, without a compiled model-release list.

#### Scenario: A newly released model appears
- **WHEN** refreshed connection discovery returns a new model
- **THEN** the owner can see and select it without a platform release, subject to current authority and supported capabilities

#### Scenario: Discovery fails
- **WHEN** discovery cannot refresh
- **THEN** cached choices are labelled stale and the app does not claim current availability

### Requirement: Current choice and durable preference are distinct
The app SHALL allow switching the interactive agent, saving a default and ordering accepted fallbacks independently of connection identity and actual execution receipts.

#### Scenario: Concurrent universe choices
- **WHEN** two owners choose different models on the same provider family
- **THEN** each next authorized inference uses its own choice without process-global preference leakage

#### Scenario: No accepted fallback
- **WHEN** the owner saves a model with an empty fallback sequence
- **THEN** exhaustion leaves that selection unchanged and does not substitute another source

### Requirement: Actual execution is visible and actionable
The typed-chat interface SHALL show a clickable active provider/model control, distinguish preference from actual execution, and remain usable without a working LLM.

#### Scenario: A router answers with another model
- **WHEN** a response reports a model different from the requested alias
- **THEN** the answering-model display uses the reported model without rewriting the saved default

#### Scenario: Model metadata is unavailable
- **WHEN** a response does not report a usable model identifier
- **THEN** the answer remains usable and the display marks the actual model unknown instead of presenting the requested alias as verified
