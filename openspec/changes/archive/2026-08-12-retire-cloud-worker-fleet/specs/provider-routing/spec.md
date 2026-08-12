## ADDED Requirements

### Requirement: Provider routing uses one assigned credential authority
Every universe-scoped provider call SHALL carry exactly one current server-resolved authority: an authenticated served request, an armed background binding, or the daemon's assigned-serving-credential context. The router SHALL attempt only the provider named by that authority and SHALL NOT read a process writer pin, fallback chain, free-provider chain, preferred-provider order, or ambient host credential to widen the route.

The assigned context SHALL carry the actual provider-work binding identity, generation, digest, assignment generation/digest, revocation generation, custody identity, and durable token/cost/invocation ceilings. The router SHALL require the canonical serving binding's `converse`/`writer` scope and SHALL reserve and reconcile durable binding spend for assigned calls. When an armed background invocation carrier is also present, its provider, assignment generation/digest, custody digest, and revocation generation SHALL match the assigned context; its exact operation and role SHALL validate without substitution, and the effective token ceiling SHALL be the lower of the binding and invocation ceilings. The serving binding validates credential assignment; the separately store-minted workflow carrier authorizes its internal operation and role without changing the selected credential.

#### Scenario: Assigned credential is the only attempted provider
- **WHEN** a daemon branch run carries an assigned credential for provider `codex`
- **THEN** the router attempts only `codex`
- **AND** a registered Claude, API-key, or local provider is never attempted for that run

#### Scenario: Missing authority holds before provider access
- **WHEN** a universe-scoped call has no current serving or background credential authority
- **THEN** it raises the typed provider-authority hold before invoking any provider

#### Scenario: Assigned provider exhaustion does not widen
- **WHEN** the provider selected by the assigned credential is unavailable, rate-limited, or exhausted
- **THEN** the call fails with evidence for that provider and does not attempt another registered provider

#### Scenario: Binding and invocation ceilings both apply
- **WHEN** an assigned workflow call also carries a single-use background invocation reservation
- **THEN** the carrier's declared operation and role are validated exactly
- **AND** the call is refused when it exceeds either the invocation ceiling or the assigned binding's remaining durable budget

#### Scenario: Retired router constructor option fails loudly
- **WHEN** a caller supplies a retired fallback, pin, or auth-health router option
- **THEN** router construction raises `TypeError` naming the retired option

### Requirement: Node policy cannot change credential authority
Per-node LLM policy SHALL be allowed to refine non-authority model settings, but any policy provider preference SHALL be ignored or rejected when it differs from the provider named by the run's assigned credential.

#### Scenario: Policy names a different provider
- **WHEN** a workflow node prefers Claude while the serving binding assigns Codex
- **THEN** the node runs only on Codex or holds
- **AND** Claude is not invoked

#### Scenario: Retired fallback-chain policy is rejected
- **WHEN** a branch policy contains `fallback_chain`
- **THEN** validation fails loudly and no provider is invoked
- **AND** the user is directed to model alternatives as explicit workflow branches with independently assigned credentials

## REMOVED Requirements

### Requirement: Every role chain terminates at the local model
**Reason**: Platform fallback chains violate exact user credential authority.
**Migration**: Assign a serving credential to each workflow; model any alternative as an explicit user-authored workflow step with its own binding.

### Requirement: Subscription-only provider policy by default
**Reason**: Credential type is user chosen in the universe vault, not a host-global provider policy.
**Migration**: Enforce credential admissibility at vault/binding boundaries and execute only the assigned credential.

### Requirement: Hard writer pin disables fallback and fails loud
**Reason**: Host writer pins are retired with provider-shaped workers.
**Migration**: Use the workflow's serving binding.

### Requirement: Per-universe engine preference and privacy allowlist
**Reason**: Preferences and allowlists are weaker duplicate routing state than the exact serving binding.
**Migration**: Use the one assigned serving credential as both selection and ceiling.

### Requirement: Auth-health quarantine of dead-login subscription providers
**Reason**: Quarantine previously skipped to another provider; assigned credential failure now holds without widening.
**Migration**: Surface assigned-credential availability as typed hold evidence.

### Requirement: Per-node policy routing honors llm_policy overrides
**Reason**: A node cannot override credential authority.
**Migration**: Retain only non-authority model settings; express provider changes as separately bound workflow design.

### Requirement: Judge ensemble fans out to all healthy judges in parallel
**Reason**: Platform fan-out spends credentials not explicitly assigned to the workflow.
**Migration**: Build an explicit multi-step judging workflow with a binding per step.

### Requirement: Chain-drain backoff prevents committing empty prose (BUG-029)
**Reason**: Chain drain cannot exist after fallback chains are removed.
**Migration**: Treat empty or unavailable output from the assigned credential as that step's explicit failure/hold.

### Requirement: The provider call bridge retries only transient full-chain exhaustion
**Reason**: Full-chain exhaustion is retired.
**Migration**: Retry only the same assigned provider when the workflow explicitly requests retry; never widen authority.
