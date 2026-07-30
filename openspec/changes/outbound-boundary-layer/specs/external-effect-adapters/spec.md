## RENAMED Requirements

- FROM: `GitHub pull-request effects apply destination gates and optional-hint receipts`
- TO: `GitHub pull-request effects apply destination gates and derived-identity receipts`
- FROM: `Windows desktop effects gate host actions but provide only narrow evidence redaction`
- TO: `Windows desktop effects gate host actions under derived-identity receipts`

## MODIFIED Requirements

### Requirement: GitHub pull-request effects apply destination gates and derived-identity receipts
The `github_pull_request` adapter SHALL parse only a matching packet from declared output keys. A packet without a destination SHALL remain on the Phase-1 dry-run compatibility path. For a destination-bearing packet, a soul-authority resolver result of denied — from a declared non-match or a soul-read failure — SHALL dry-run, while undeclared authority SHALL fall through to the legacy gates owned by `external-effect-receipts`. A real write SHALL require an exact destination capability and consent; a bound vault credential SHALL outrank environment-vended credentials and SHALL never be returned in Branch-visible evidence. Every effect SHALL use the shared atomic receipt lifecycle under a system-derived effect identity; a packet with no derivable identity SHALL be refused rather than proceeding unreceipted. The adapter SHALL journal intent before materializing remote state, so a failure after partial materialization is recoverable rather than silent. A successful external write whose receipt finalization fails SHALL return success evidence marked `receipt_finalize_failed` and SHALL enqueue destination reconciliation for that identity.

#### Scenario: Missing consent remains a dry run
- **WHEN** a valid destination packet has a credential but no active consent row
- **THEN** the adapter returns destination-specific dry-run evidence and performs no GitHub write

#### Scenario: Concurrent reservation prevents duplicate PRs
- **WHEN** another run holds the reservation for the same derived effect identity
- **THEN** the adapter returns `reason=concurrent_in_flight` without invoking PR creation

#### Scenario: Successful duplicate returns recorded evidence
- **WHEN** the idempotency receipt already records a successful PR for that identity
- **THEN** the adapter returns a dedup hit with that evidence and performs no external write

#### Scenario: A packet without a derivable identity is refused
- **WHEN** an otherwise authorized destination packet yields no derivable goal, schedule-period, and item identity
- **THEN** the adapter refuses the effect instead of creating an unreceipted PR

#### Scenario: PR failure after materialization is journaled for reconciliation
- **WHEN** remote branch materialization succeeds but PR creation fails
- **THEN** the adapter returns failure evidence, releases the reservation, and leaves a journal entry naming the already-created remote objects and ref for reconciliation

### Requirement: Typed GitHub pull-request reconciliation is destination-authoritative
The outbound owner SHALL accept only a closed server-authored GitHub
pull-request effect identity containing the exact universe, automation, claim,
repository, intended head SHA, and fixed effect kind. It SHALL derive a
versioned SHA-256 marker from canonical identity bytes, expose only that digest
marker at the destination, and reconcile read-only through GitHub's pull
requests associated with the intended commit using a destination-matched,
read-scoped, credential-blind connection proxy. The reconciler SHALL NOT
receive credential material. Legacy or Branch-authored packet fields SHALL NOT
create this identity or reconciliation authority.

Exactly one result with the exact repository, head SHA, and marker SHALL be
terminal success. A successful authoritative query with no exact result SHALL
be terminal absence. Multiple exact matches, partial matches, malformed
responses, and destination errors SHALL be indeterminate and SHALL NOT permit
another write.

#### Scenario: one exact remote pull request is attached
- **WHEN** reconciliation finds exactly one pull request associated with the intended commit whose head SHA and body marker match the server-authored identity
- **THEN** it returns terminal success with bounded pull-request evidence and performs no mutation

#### Scenario: authoritative absence permits the owner to consider one retry
- **WHEN** the commit-association query succeeds and contains no pull request matching both the exact head SHA and marker
- **THEN** reconciliation returns terminal absence without creating, editing, or closing a pull request

#### Scenario: ambiguous remote state remains held
- **WHEN** the query fails, is malformed, returns multiple exact matches, or returns only a partial match
- **THEN** reconciliation returns indeterminate evidence and grants no retry or effect authority

### Requirement: Windows desktop effects gate host actions under derived-identity receipts
The host-local Windows desktop adapter SHALL require explicit affirmative user approval in the packet, exact per-universe consent, and an attested interactive Windows desktop runtime before any host action. A missing approval SHALL error, missing consent SHALL dry-run, and a non-Windows or non-interactive runtime SHALL return `no_host_available` before a receipt or action. Every action SHALL use shared duplicate/in-flight reservation handling under a system-derived effect identity; an action with no derivable identity SHALL be refused rather than proceeding unreceipted. The default action runner SHALL return stable handles for action paths, and evidence redaction SHALL remain a narrow, explicitly scoped mechanism rather than a general confidentiality boundary; that limitation SHALL be stated wherever the evidence is surfaced. A successful action whose receipt finalization fails SHALL remain successful evidence marked `receipt_finalize_failed` and SHALL enqueue reconciliation for that identity.

#### Scenario: User approval is mandatory
- **WHEN** a Windows desktop packet lacks affirmative user approval or contains negative approval text
- **THEN** the adapter returns `approval_required` before checking consent, reserving a receipt, downloading, or launching anything

#### Scenario: Wrong runtime is refused before action
- **WHEN** approval and consent exist but runtime attestation is not an interactive Windows desktop
- **THEN** the adapter returns `no_host_available` and performs no host-local action

#### Scenario: Default action paths use handles but attestation retains home
- **WHEN** an approved, consented action succeeds using the default action runner and auto-generated runtime attestation
- **THEN** action receipts use stable path handles while the appended runtime attestation still contains its raw `home` string

#### Scenario: An action without a derivable identity is refused
- **WHEN** all host gates pass but no effect identity can be derived for the action
- **THEN** the adapter refuses the action instead of performing an unreceipted host effect
