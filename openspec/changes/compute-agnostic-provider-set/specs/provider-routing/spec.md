# provider-routing (delta)

## MODIFIED Requirements

### Requirement: User-brought compute of any allowed access method

The platform SHALL NOT enumerate a compiled provider set. A universe runs on compute
the user brings, of any allowed access method — subscription (via CLI), API key (via
HTTP), or another published standard — never on platform-supplied compute. This
REPLACES the "subscription-only by default" requirement: subscription is one access
method, not the only one. "No host writer ever" is preserved — the compute is always
the user's own. API-key providers are honored only when the credential is held under
the custody owner's contract (no raw key in the control plane / JSON vault).

#### Scenario: an api-key provider serves a universe

- **GIVEN** a universe whose owner has registered an `api_key_http` provider
  definition and deposited its credential through the custody owner's path
- **WHEN** the universe runs a turn selecting that provider
- **THEN** the turn executes on that provider via the HTTP protocol encoder over the
  outbound proxy, drawing on the user's own credential, with no platform fallback

#### Scenario: no compute without a user-authorized provider

- **GIVEN** a universe with no enrolled requester-owned provider
- **WHEN** a turn or automation attempts to run
- **THEN** it fails closed (`no_requester_owned_executor`), never borrowing an ambient
  host credential and never falling back to a platform-supplied model

### Requirement: Role chains resolve through the open routing equation

Routing SHALL resolve candidates through the equation `selected ordered candidates ∩
allowed_providers ceiling ∩ live requester-owned enrollment ∩ request capability`,
not a static per-role provider list. The router filters WITHIN the selected ordered
set and never synthesizes a candidate the selection did not produce. The existing
fail-loud, bounded-cooldown, hard-writer-pin, and per-universe privacy-allowlist
requirements are preserved unchanged; the privacy ceiling DOMINATES capability
routing (capability may only narrow, never widen or override a privacy exclusion).

#### Scenario: router never adds an unselected provider

- **GIVEN** an ordered selected set `[A, B]` and an enrolled-but-unselected provider C
- **WHEN** both A and B are exhausted or capability-filtered out
- **THEN** the call fails closed naming the empty effective set — C is never invoked

#### Scenario: privacy ceiling dominates capability

- **GIVEN** a provider that is capability-best for the request but excluded by the
  universe privacy allowlist
- **WHEN** the router resolves candidates
- **THEN** the excluded provider is never selected, regardless of capability rank

## ADDED Requirements

### Requirement: Providers are open, user-defined definitions; registration is not authority

A universe owner SHALL be able to register a compute provider definition for any
reachable provider by describing it (access method, protocol shape, endpoint, model)
without a code change or a platform allowlist. A registered definition is an immutable,
server-issued-id descriptor and creates ONLY a candidate: it does not enroll,
authorize, select, or make the provider routable. `allowed_providers` and selection
resolve stable server-issued definition/binding ids, never user-chosen labels.

#### Scenario: registering a novel provider creates a candidate only

- **GIVEN** an owner who registers a provider we never integrated (e.g. Kimi)
- **WHEN** registration succeeds
- **THEN** a `ProviderDefinition` with a server-issued id exists, but the provider is
  not enrolled, not selected, and not routable until the downstream owners act

#### Scenario: a commons/remixed definition never carries a credential

- **GIVEN** a provider definition published to the commons by another user
- **WHEN** a second user remixes it into their universe
- **THEN** they receive the descriptor only, and must supply their own credential
  through the custody owner — the original owner's credential is never auto-bound

### Requirement: Access-method executors are selected by provenance with no cross-method fallback

Execution SHALL select an executor deterministically by the definition's access
method: `subscription_cli` selects the vendor CLI adapter (preserving the existing
`codex exec` sandbox/auth-health/budget/telemetry behavior and the `codex` identity);
`api_key_http` selects an HTTP protocol encoder over the SSRF-hardened outbound proxy
(never a vendor SDK pointed at an arbitrary `base_url`). A failed subscription-CLI
provider SHALL NOT fall back to an SDK/API using ambient credentials.

#### Scenario: api_key_http never bypasses the outbound proxy

- **GIVEN** an `api_key_http` provider with a user-supplied `base_url`
- **WHEN** a turn executes on it
- **THEN** the request goes through the credential-blind outbound proxy with full SSRF
  enforcement (HTTPS-only, private/loopback/metadata blocked, DNS revalidated,
  redirects/env-proxies disabled), and the credential ref is bound to the registered
  endpoint so a changed `base_url` cannot redirect the key

#### Scenario: subscription CLI does not silently degrade to an API

- **GIVEN** a `subscription_cli` provider whose CLI auth is unhealthy
- **WHEN** routing evaluates it
- **THEN** it is skipped by the existing auth-health quarantine — never retried as an
  API/SDK call on an ambient credential

### Requirement: Capability observations and compliance advisories are not authority

Capability observations and compliance advisories SHALL be advisory only: neither
SHALL grant, widen, or veto execution authority, and they MUST only narrow an
already-authorized route or inform the UX. Capability observations comprise
user-declared capabilities (validated on use), passive health/rate observations from
real calls, and at most one bounded same-origin `/models` probe (TTL, per-owner
rate/concurrency/cost limited, cache keyed by connection generation). Compliance
advisories are freshness-stamped, provenance-carrying "what's allowed" records. Hard
prohibitions SHALL be enforced at the access-method/connect boundary, not as a
routing-time authority decision.

#### Scenario: an advisory cannot widen authority

- **GIVEN** a compliance advisory marking a provider as "allowed" for a use case
- **WHEN** that provider is outside the `allowed_providers` ceiling or unenrolled
- **THEN** it is still not routable — the advisory does not add authority

#### Scenario: capability filter only narrows

- **GIVEN** a capability observation that a selected provider cannot serve the request
- **WHEN** the router resolves candidates
- **THEN** that provider is removed from the effective set; no new provider is added
  to compensate
