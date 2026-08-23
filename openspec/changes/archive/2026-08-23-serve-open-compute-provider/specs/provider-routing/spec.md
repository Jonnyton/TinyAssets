# provider-routing (delta)

## ADDED Requirements

### Requirement: A universe can serve on a registered open compute provider

A universe owner SHALL be able to serve converse/writer turns on a registered open
(`api_key_http`) compute provider, authorized SOLELY by the connection grant (no
subscription snapshot or custody), through the SAME served-authority /
assignment / work-binding / CAS machinery as subscription providers — via one
`ServedProviderAuthority` with an explicit `authority_kind` discriminator
(`subscription_snapshot` | `connection_grant`), never inferring the open kind from a
missing snapshot. The credential SHALL be resolved only inside the credential-blind
broker at call time; the control plane holds a grant reference, never the secret. The
subscription-CLI serving path SHALL be behaviorally unchanged.

#### Scenario: Open provider serves a converse turn

- **GIVEN** an owner who registered an `api_key_http` provider (`connect_compute`) whose
  connection grant is current + bound to the universe, and selected it via
  `set_engine open_provider`
- **WHEN** a converse/writer turn runs for that universe
- **THEN** a `connection_grant`-kind served authority is minted (no snapshot/custody), the
  turn executes on that provider through the credential-blind proxy, and the reservation
  is scoped by the work-binding id/generation

#### Scenario: Open serving respects the allowed_providers ceiling

- **GIVEN** an open provider not within the universe's `allowed_providers`
- **WHEN** serving is attempted
- **THEN** it is refused — a minted served authority does NOT bypass the ceiling

#### Scenario: Cross-universe / revoked / substituted grant is refused

- **GIVEN** an open provider whose grant is bound to another universe, revoked, or whose
  registered executor instance's definition/grant identity does not match the authority
- **WHEN** authorization, reservation, or launch runs
- **THEN** it fails closed (`ProviderAuthorityHeldError`) with no ambient fallback, and a
  possibly-dispatched request CONSUMES (never releases) its reservation

#### Scenario: An absent open snapshot never becomes open authority

- **GIVEN** a `subscription_snapshot` authority whose snapshot is unexpectedly absent
- **WHEN** it is evaluated
- **THEN** it fails closed — the missing snapshot is NOT treated as a `connection_grant`
  (kind is explicit, never inferred)
