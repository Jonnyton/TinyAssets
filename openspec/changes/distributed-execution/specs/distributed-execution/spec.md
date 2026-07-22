# Distributed execution

## ADDED Requirements

### Requirement: Authority derives only from signatures, content addresses, or external re-confirmation

Every authority decision in the execution path SHALL derive from one or more of:
a platform-verified signature (M1), a caller-held content address re-derived at
the decision point (M2), or fresh re-confirmation from the authoritative external
system (M3). Mutable or INSERT-able database state SHALL only narrow, reject, or
serve as audit log, and SHALL NEVER be the sole basis for a positive authority
decision.

#### Scenario: Forged row cannot grant a lease

- **GIVEN** an attacker with direct DML on the lease store
- **WHEN** they doctor any row or INSERT into an append-only events table
- **THEN** completion, candidate acceptance, and replay SHALL reject the result,
  because authority is checked against the platform signature and re-derived
  facts, not the row.

#### Scenario: Restart re-derives the same terminal fact

- **GIVEN** a job that reached signed terminal acceptance
- **WHEN** the process restarts and replays from the signed attestation
- **THEN** it SHALL return the identical terminal receipt, and a reset terminal
  row without a valid attestation SHALL fail closed.

#### Scenario: Mutable branch-version columns cannot replace requested content

- **GIVEN** a caller requests execution by a full branch snapshot content address
- **WHEN** direct DML changes both the stored snapshot and its adjacent stored hash
- **THEN** execution SHALL reject the row because the snapshot digest is re-derived
  and compared with the caller-held content address at the execution decision.

### Requirement: Signed records use immutable per-domain field contracts

The record verifier SHALL NOT accept a caller-supplied set of unchecked fields. A
domain separator SHALL select one immutable contract that partitions every signed
field as row-bound, specialized-validated, or inert. An unknown domain, or a
signed field not classified by the domain contract, SHALL fail closed.

#### Scenario: Caller cannot neutralize verification

- **GIVEN** a consumer verifying a signed record
- **WHEN** it attempts to declare an authority-bearing field as unchecked
- **THEN** verification SHALL reject it, because field accounting is fixed by the
  registered domain contract, not by the caller.

### Requirement: Device identity is recomputed, never trusted from adjacent columns

The platform SHALL recompute every derived identity value at every consumption
site. Where a derived value (e.g. a key thumbprint) is stored beside the value it
derives from (e.g. a public key), the platform SHALL reject any row whose stored
derived value does not bind its source value.

#### Scenario: Single-column key substitution is rejected

- **GIVEN** `enrolled_daemons` with `ed25519_public_key` and `key_thumbprint`
- **WHEN** an attacker rewrites only the public-key column via DML
- **THEN** enrollment completion, challenge creation, token issuance, device-key
  resolution, and request verification SHALL all reject the daemon, because the
  thumbprint is recomputed from the key and no longer binds.

### Requirement: An owner-daemon executes over an authenticated protocol

A job SHALL be claimed and completed only by a daemon the control plane
authenticated for that job's owner, over an authenticated transport. The signed
grant SHALL bind owner, daemon, job, capsule, lease, and fence; the completion
SHALL be fenced and produce a signed terminal attestation.

#### Scenario: A daemon claims and completes a real job

- **GIVEN** an enrolled daemon holding its device key and an access token
- **WHEN** it claims a persisted job, executes it, submits a device-signed
  candidate plus content-addressed blobs, and requests completion
- **THEN** the platform SHALL fence-complete and persist a signed terminal
  attestation, and a claim signed by a different owner's daemon SHALL be rejected
  with no lease created.

### Requirement: The GitHub effect is exactly-once and never merges

Consuming an accepted result SHALL produce at most one result-bound branch and
one reviewable pull request across retries and crashes. The effect SHALL NOT hold
approve or merge authority, use an ambient token, accept a caller-selected
repository, or write against a stale head.

#### Scenario: Retried effect does not double-open

- **GIVEN** an accepted result whose effect was interrupted mid-open
- **WHEN** the effect route runs again
- **THEN** it SHALL reconcile to the same single branch and PR rather than opening
  a second one.

### Requirement: Live authority surfaces roll out staged and host-gated

Live authority paths SHALL roll out through a bounded dual-verify window with
explicit host go/no-go per surface, and MUST NOT be dark-cut autonomously. This
covers WorkOS enforcement, market settlement, and GitHub merge.

#### Scenario: A live path keeps serving during migration

- **GIVEN** a live authority surface being migrated to the signed model
- **WHEN** the new mechanism is introduced
- **THEN** the old path SHALL keep serving until the host approves cutover, and
  both SHALL be verified to agree during the window.
