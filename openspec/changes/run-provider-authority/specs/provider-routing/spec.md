## ADDED Requirements

### Requirement: Foreground prompt runs derive exact provider authority from the active serving assignment
A user-authorized foreground Branch run that reaches a prompt node SHALL derive
provider authority from the owner's current ACTIVE serving assignment for that
universe. Each actual provider attempt SHALL use a distinct, one-use run carrier
bounded by the immutable Branch subject, exact provider assignment, owner,
universe, role, invocation budget, token budget, cost budget, expiry, and current
parent binding. Subscription providers SHALL receive only a sealed run-scoped
credential snapshot. Registered open (`api_key_http`) providers SHALL receive no
subscription snapshot and SHALL continue through their current connection-grant
custody and the credential-blind outbound proxy. Provider registration alone
SHALL NOT authorize a foreground run.

#### Scenario: The selected subscription provider runs once
- **GIVEN** a user-authorized foreground Branch run with one prompt node and a current ACTIVE subscription-backed serving assignment whose exact provider is allowed by the node policy
- **WHEN** the node requests its provider completion
- **THEN** one run carrier is reserved and consumed, the selected provider is invoked exactly once with its sealed run-scoped snapshot, and the reservation settles from the actual outcome

#### Scenario: The selected open provider runs once
- **GIVEN** a user-authorized foreground Branch run with one prompt node and a current ACTIVE registered open provider whose connection grant is current, universe-bound, and allowed by the node policy
- **WHEN** the node requests its provider completion
- **THEN** one run carrier is reserved and consumed, and the exact open provider is invoked exactly once through the credential-blind proxy without a subscription snapshot
- **AND** the reservation settles `succeeded` only when the provider supplies complete trustworthy token and cost telemetry; otherwise it settles `indeterminate` and remains conservatively charged without inventing zero-cost usage

#### Scenario: Registration without active serving selection grants nothing
- **GIVEN** a registered open provider that is not the owner's current ACTIVE serving assignment for the run's universe
- **WHEN** a foreground prompt node requests a provider completion
- **THEN** the run fails with `permission_denied:provider_not_bound`, no provider is invoked, and no effect fires

#### Scenario: Any authority mismatch launches nothing
- **GIVEN** a foreground prompt run whose serving authority is missing, stale, revoked, cross-universe, owned by another principal, outside the node policy, or no longer matches the exact current assignment
- **WHEN** provider admission or an attempt is evaluated
- **THEN** the run fails closed with `permission_denied:provider_not_bound`, no different or ambient provider is substituted, and no effect fires
