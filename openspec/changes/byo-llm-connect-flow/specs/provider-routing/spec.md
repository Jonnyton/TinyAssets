# Provider routing

## MODIFIED Requirements

### Requirement: Served turns use only fresh universe-owned provider authority

Every universe-scoped provider call SHALL pass served-authority validation;
universe configuration and process configuration are projections, never
authority. A `converse` call is eligible only when the explicitly carried
current-request capability, selected agent binding and revision,
requester-local assignment, active `ProviderWorkBinding`, and current opaque
vault custody reference all agree on the authenticated founder, universe,
provider, generations, digests, operation, role, expiry, and budgets. The
authorized chain SHALL contain exactly that provider and SHALL never widen to
an ambient host credential, runtime preference, default chain, or another
universe's binding. Other universe-scoped operations SHALL hold until an exact
server authority for that operation exists.

#### Scenario: Exact served authority is current

- **WHEN** a founder `converse` request carries one live server-issued request
  lease and every selected server-held record is fresh and exact
- **THEN** the router calls only the assignment's provider under its token,
  cost, and invocation ceilings

#### Scenario: No universe-authorized serving binding

- **WHEN** the served request has no current serving binding or any selected
  principal, revision, assignment, binding, custody, operation, role,
  generation, digest, state, expiry, or budget check fails
- **THEN** the router raises the typed provider-authority hold with
  connect-provider guidance before provider or credential access
- **AND** no ambient provider is attempted

#### Scenario: Configuration names a provider without live authority

- **WHEN** a universe-scoped call, including `run_graph`, has provider
  preferences or an allowlist but no matching live server-issued authority
- **THEN** the call holds before provider access
- **AND** configuration alone cannot select or invoke a provider

#### Scenario: Credential rotates after request selection

- **WHEN** the vault custody record changes after the agent was selected but
  before the sink validates it
- **THEN** the call holds and the provider receives zero calls

### Requirement: Provider request authority originates at the current message

Authenticated MCP provider authority SHALL be re-derived only from
`request_ctx.get().request` for the exact non-deferred `tools/call` message.
Middleware SHALL reserve a one-shot principal/session/request/tool token, the
registered wrapper SHALL claim it in the actual worker, and both boundaries
SHALL revoke it before result release. Outer ASGI identity, inherited or
snapshotted HTTP helpers, initialize state, anonymous wiki-canary authority,
serialized lookalikes, and prior-message state SHALL grant no provider
authority. Signed founder Slack ingress SHALL mint the same bounded capability
class with its exact app-ingress mechanism and routed agent revision.

#### Scenario: Outer request identity exists without current message request

- **WHEN** an authenticated outer ASGI context exists but the FastMCP
  per-message request is absent
- **THEN** middleware mints no provider reserve or capability

#### Scenario: Signed founder Slack event

- **WHEN** the HMAC-authenticated app ingress recognizes a current founder and
  routes an exact channel binding
- **THEN** it claims one app-event request capability bound to the founder,
  event, session, mechanism, issuer, and routed agent revision
- **AND** revokes it after the synchronous turn returns

### Requirement: Assignment readers and writers are requester-local fenced

Provider launch SHALL hold a cross-process shared canonical-universe admission fence from
fresh validation through provider completion. Assignment publication,
credential-vault replacement, provider-reference changes, and serving-state
changes SHALL use the exclusive side of the same non-reentrant fence. A writer
SHALL wait for active served calls, and reverse or reentrant acquisition SHALL
fail loudly.

#### Scenario: Credential writer races a served launch

- **WHEN** a credential or assignment writer requests the exclusive fence
  while a served call holds the shared fence
- **THEN** the writer waits until the call releases it
- **AND** no call observes a mixed assignment/custody generation

### Requirement: Served-call budgets are durable launch authority

Immediately before provider launch, the router SHALL atomically revalidate the
assignment and credential generation and reserve invocation, token, and cost
budget in the authority database. Concurrent reservations, completed usage,
and indeterminate failures SHALL count against the exact binding generation.
After completion, actual adapter usage SHALL be recorded; an over-ceiling result
SHALL be withheld and future calls SHALL remain held.

#### Scenario: Provider exceeds a reserved ceiling

- **WHEN** actual token or cost usage exceeds the durable reservation
- **THEN** the result is withheld and the reservation is marked exceeded
- **AND** no later call can reuse the consumed budget

### Requirement: Bindable Codex serving runs in an OS sandbox

A served Codex adapter call SHALL execute under an external OS sandbox that
read-only mounts the selected universe, exposes only its contained Codex auth
home, disables Codex shell execution and user/project rules, and emits
machine-readable usage accounting. If the sandbox or accounting output is
unavailable, the adapter SHALL fail closed before returning a reply.

#### Scenario: Sandboxed Codex turn completes

- **WHEN** a live Codex serving authority reaches the real adapter
- **THEN** Codex runs inside the OS sandbox and returns its reply plus token
  accounting
- **AND** no unconfined fallback launch is attempted
