## ADDED Requirements

### Requirement: Stable account-bound host principals remain distinct from host-pool sessions

TinyAssets SHALL represent an authenticated local installation with an opaque,
stable, server-issued `host_principal_id` bound to the verified account and
device proof. Existing host-pool `host_id` rows SHALL remain ephemeral
capability/availability sessions: repeated registration SHALL continue to
insert distinct rows, heartbeat SHALL update the selected row, and exact
deregistration SHALL delete only the supplied session row. Every authenticated
production session SHALL reference its stable principal and exact
`host_principal_generation`. Registration and heartbeat SHALL require current
generation device proof. Exact deregistration SHALL require the same proof,
exact session ID, and mutation idempotency without using the session ID,
caller-supplied owner, or tray-local UUID as principal authority.

Legacy or development no-auth rows MAY remain readable and operable within
their explicitly isolated development scope, but SHALL be marked unattested
and SHALL NOT satisfy provider-custody, network/paid visibility, distributed
execution, market, settlement, or other verified-host authority.

#### Scenario: One principal owns multiple host sessions

- **WHEN** one authenticated host principal registers the same or different capabilities more than once
- **THEN** each registration creates a distinct host-pool session row carrying the same stable principal reference and current generation
- **AND** deleting one session leaves the principal and sibling sessions intact

#### Scenario: Deregistration is exact and retry-safe

- **WHEN** a current-generation host proves and idempotently deregisters one exact session ID
- **THEN** only that session is deleted and response-loss retry returns the same deleted result
- **AND** the principal and every sibling session remain intact

#### Scenario: Session identity cannot substitute for principal identity

- **WHEN** a caller presents only a host-pool session ID, caller-supplied owner, heartbeat, capability grant, or tray-local UUID
- **THEN** any operation requiring verified host-principal authority fails before downstream mutation
- **AND** no session attribute is promoted or inferred into a stable principal

#### Scenario: Revoked principal fences attached sessions

- **WHEN** a stable host principal becomes revoked or expired
- **THEN** every attached session becomes ineligible at the next authority check and before protected work starts or commits
- **AND** heartbeat or re-registration cannot reactivate that principal

#### Scenario: Mixed-version and zero-host operation fail closed

- **WHEN** an old client, an unattested legacy row, a stale principal generation, or zero daemon hosts are online
- **THEN** no verified-host authority is inferred and durable platform surfaces remain available without maintainer compute
- **AND** rollback disables new writers/consumers instead of accepting a tray UUID, MCP-audience token, or missing generation

### Requirement: Host-principal evidence grants no compute or economic authority

An active host principal SHALL prove only that one verified account bound one
device key. It SHALL NOT by itself grant provider or credential access,
compute eligibility, network/paid visibility, work claim or execution
authority, universe access, market participation, lease, settlement, spending,
or maintainer/founder resources. Each consumer SHALL validate its own separate
authority and exact scope.

#### Scenario: Verified host without consumer authority remains ineligible

- **WHEN** a host has an active principal but lacks the selected consumer's capability, assignment, visibility, execution-grant, market, or payment authority
- **THEN** that consumer fails closed before work, provider, credential, lease, settlement, or spending access
- **AND** no maintainer credential, quota, account, model, or hardware is substituted

#### Scenario: Custody checks two independent generations

- **WHEN** provider custody or invocation consumes a host principal
- **THEN** it verifies the current host-principal generation and its separate provider-assignment generation at the authority boundary
- **AND** neither a client response nor host-pool session row is accepted as control-plane evidence
