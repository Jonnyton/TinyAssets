## ADDED Requirements

### Requirement: Accepted-market activation is bound to exact live requester authority

The identity boundary SHALL authorize
`write_graph(target="engine", action="activate_accepted_market")` only from the
current authenticated Streamable-HTTP request and SHALL bind the one-shot
activation authority to the exact request, session, tool, action, principal,
tenant, and target universe. The server MUST derive principal and tenant from
the verified transport context, require write or admin authority for the
universe, and refuse caller-supplied actor, tenant, delegation, credential,
provider, host, wallet, or execution-grant authority.

#### Scenario: authenticated universe writer may request exact activation

- **WHEN** a verified connector principal with write authority invokes the engine activation action for the bound universe
- **THEN** the identity boundary supplies one request-local activation authority bound to that principal, tenant, universe, session, tool, target, and action
- **AND** that identity authority alone does not authorize provider or remote execution

#### Scenario: cross-universe or caller-authored identity is refused

- **WHEN** the caller lacks write authority for the target universe or supplies actor, tenant, delegation, provider, host, credential, wallet, or execution-grant fields
- **THEN** activation is refused before market acceptance or engine assignment mutates

### Requirement: Activation authority is one-shot and cannot escape its connector invocation

The activation authority SHALL be non-serializable, non-delegable, and
non-replayable outside its originating invocation. Background, scheduled,
deferred, task-augmented, stdio, SSE, and unauthenticated calls MUST NOT mint
or recover it, and a later `converse` MUST independently derive its own valid
identity and execution authority rather than reuse the activation capability.

#### Scenario: copied activation material grants no authority

- **WHEN** a serialized value, stale prior-request value, mismatched session/tool/action value, or background invocation attempts accepted-market activation
- **THEN** the identity boundary fails closed and no accepted agreement, B2/B13 binding, or engine assignment is created

#### Scenario: user-authored automation receives no privileged identity path

- **WHEN** a user-built or remixed task automation invokes engine activation outside a current authenticated connector request
- **THEN** it receives no special platform or cheat-loop authority and must satisfy the same public identity and execution contracts as any other graph work

### Requirement: Identity success composes atomically without becoming execution authority

The activation composition boundary SHALL combine verified requester identity,
universe authorization, a current accepted paid-market agreement, and the
current non-executable B13-bound activation grant before publishing
`engine_source="accepted_market"`,
`engine_assignment_state="remote_ready"`, and `allowed_providers=[]`. Identity,
OAuth, role, founder status, or universe ownership MUST NOT substitute for the
activation grant or the separate exact per-job B2 grant. A failed composition
SHALL publish no partial activation state.

#### Scenario: complete authority publishes remote-ready state

- **WHEN** the exact authenticated requester accepts valid bounded market terms and the B13 root returns a current universe-bound non-executable activation grant
- **THEN** the composition atomically records the owner references and publishes `accepted_market + remote_ready + []`
- **AND** no maintainer credential, quota, wallet, compute, desktop, or environment fallback participates

#### Scenario: identity without execution grant remains held

- **WHEN** requester identity and universe access are valid but paid-market or B13-bound activation authority is absent, expired, revoked, fenced, cancelled, or inconsistent
- **THEN** no remote-ready assignment is published and the connector returns a typed refusal or accepted-market repair state
- **AND** identity authority is not promoted into provider or execution authority
