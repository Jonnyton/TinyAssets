## ADDED Requirements

### Requirement: Requester-owned automations are claimed on their provider binding

A requester-owned automation's claimable executor SHALL be derived from its
provider binding, not from a named maintainer daemon identifier. Any executor
holding a live, compatible, requester-owned binding SHALL be eligible to claim
it, and no single named daemon SHALL be a required path for requester-owned
work.

#### Scenario: an unrelated maintainer daemon is offline
- **WHEN** a requester-owned automation is active and the maintainer drain daemon has no live runtime instance
- **THEN** any other executor holding a compatible live requester-owned binding may claim and execute it

#### Scenario: no compatible executor
- **WHEN** no executor holds a live compatible binding
- **THEN** the automation remains unclaimed, reports that it is awaiting compatible capacity, and no maintainer-owned credential is substituted

### Requirement: One owner runs multiple automations concurrently

An owner SHALL be able to hold multiple active automations at once. Their
execution SHALL be bounded only by each automation's declared budgets and
available compatible capacity, and one automation SHALL NOT block another
belonging to the same or a different owner.

#### Scenario: two active automations for one owner
- **WHEN** an owner has two active automations and compatible capacity exists for both
- **THEN** both may be claimed and executed without one waiting on the other's terminal receipt

### Requirement: Blocked activation reports a blocker and a next action

The health record SHALL carry a non-null blocker describing the cause and a
non-null next action describing what would resolve it, whenever an automation's
health state is not a running state.

#### Scenario: activation is stopped
- **WHEN** an automation is desired-active but its activation state is stopped
- **THEN** health reports a non-null blocker and a non-null next action rather than null for both

#### Scenario: awaiting capacity
- **WHEN** an automation cannot be claimed because no compatible executor is live
- **THEN** the blocker names the missing capacity and the next action names what must become available

### Requirement: Provider policy is recorded as nominal identifiers only

Provider policy on authority records SHALL hold only nominal provider
identifiers. It SHALL NOT carry a credential, a credential reference, or any
bearer-shaped value, and SHALL remain subject to the existing non-bearer
reference rules for identity fields.

#### Scenario: provider policy carries no credential
- **WHEN** provider selection or fallback policy is recorded on an authority record
- **THEN** it holds only nominal provider identifiers and no credential or credential reference

#### Scenario: credential-shaped provider value is refused
- **WHEN** a record carries a credential- or bearer-shaped value in a provider policy field
- **THEN** the record is refused
