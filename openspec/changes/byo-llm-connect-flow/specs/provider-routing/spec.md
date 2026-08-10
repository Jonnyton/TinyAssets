# Provider routing

## MODIFIED Requirements

### Requirement: Served turns use only fresh universe-owned provider authority

For operation `converse`, the router SHALL fail closed unless the explicitly
carried current-request capability, selected agent binding and revision,
requester-local assignment, active `ProviderWorkBinding`, and current opaque
vault custody reference all agree on the authenticated founder, universe,
provider, generations, digests, operation, role, expiry, and budgets. The
authorized chain SHALL contain exactly that provider and SHALL never widen to
an ambient host credential, runtime preference, default chain, or another
universe's binding.

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

Provider launch SHALL hold a shared canonical-universe admission fence from
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
