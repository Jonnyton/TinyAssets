## ADDED Requirements

### Requirement: Declared node effects dispatch after run completion without changing terminal success
After a normal or resumed Branch run completes, the runtime SHALL inspect each node's declared `effects`, find matching packets only in that node's declared output keys, and dispatch the registered sink adapter. It SHALL store per-node, per-sink evidence in system-authored `external_write_results` and flatten adapter failures into `external_write_errors`; a missing packet, refusal, adapter exception, or external failure SHALL remain structured evidence and SHALL NOT raise through or reverse the completed run status. Nodes without declared effects SHALL produce no adapter work.

#### Scenario: Declared sink receives its matching packet
- **WHEN** a completed node declares a supported effect and one declared output key contains that sink's packet
- **THEN** the runtime dispatches that adapter and records its result under the node and sink in `external_write_results`

#### Scenario: Adapter failure does not fail the run
- **WHEN** an adapter refuses, returns an error, or raises during completion dispatch
- **THEN** the runtime records structured effect evidence and the Branch run remains completed

#### Scenario: Resume completion also dispatches effects
- **WHEN** a previously interrupted run reaches completion through `resume_run`
- **THEN** its declared effects use the same dispatch and evidence path as an initial completion

### Requirement: External-write receipt keys are system-authoritative and visible in run snapshots
Before adapter dispatch the runtime SHALL move any Branch-authored `external_write_results` or `external_write_errors` value to the corresponding `_branch_authored_*` quarantine key. System-generated adapter evidence SHALL then own the canonical keys. The composed run snapshot SHALL expose canonical external-write results and errors from persisted run output so callers do not need a separate output-only read.

#### Scenario: Forged result is quarantined
- **WHEN** Branch output already contains `external_write_results`
- **THEN** the value is moved to `_branch_authored_external_write_results` before system adapter evidence is written at the canonical key

#### Scenario: Snapshot exposes system receipt
- **WHEN** a completed run persisted adapter evidence
- **THEN** the run snapshot includes its `external_write_results` and any `external_write_errors`

### Requirement: GitHub pull-request effects require destination authority, consent, and atomic idempotency
The `github_pull_request` adapter SHALL parse only a matching packet from declared output keys. A destination-bearing real write SHALL require a destination-scoped capability credential, an active per-universe consent for the exact sink and repository, and an atomic receipt reservation; a bound vault credential SHALL outrank environment-vended credentials and SHALL never be returned in Branch-visible evidence. Missing gates, a concurrent reservation, or an operator dry-run SHALL return dry-run evidence. A successful reservation SHALL create the PR and finalize evidence; a succeeded duplicate SHALL return recorded evidence without another PR, and receipt-store errors SHALL fail closed as structured errors.

#### Scenario: Missing consent remains a dry run
- **WHEN** a valid destination packet has a credential but no active consent row
- **THEN** the adapter returns destination-specific dry-run evidence and performs no GitHub write

#### Scenario: Concurrent reservation prevents duplicate PRs
- **WHEN** another run holds the same idempotency reservation
- **THEN** the adapter returns `reason=concurrent_in_flight` without invoking PR creation

#### Scenario: Successful duplicate returns recorded evidence
- **WHEN** the idempotency receipt already records a successful PR
- **THEN** the adapter returns a dedup hit with that evidence and performs no external write

### Requirement: GitHub merge effects bind authorization to branch protection and exact head SHA
The `github_merge` adapter SHALL require a valid repository destination, positive PR number, one of `merge`, `squash`, or `rebase`, authorization mode `github_branch_protection`, a destination capability, and a 40-character expected head SHA. It SHALL fetch the current PR and reject a mismatched head before calling the merge endpoint; wiki positions SHALL be audit context only and SHALL NOT authorize merging. The operator external-write kill switch, missing capability, missing authorization, stale head, or branch-protection rejection SHALL fail closed as structured evidence.

#### Scenario: Expected head mismatch refuses stale authorization
- **WHEN** the current PR head differs from the packet's expected head SHA
- **THEN** the adapter returns a stale-authorization error and does not call the merge endpoint

#### Scenario: Branch protection authorizes a bound merge
- **WHEN** destination capability is present, authorization mode is branch protection, the expected head matches, and GitHub accepts required checks/reviews
- **THEN** the adapter submits the selected merge method bound to that head and returns merge evidence

#### Scenario: Wiki position cannot authorize merge
- **WHEN** a packet supplies review context but omits `github_branch_protection` authorization
- **THEN** the adapter returns `missing_merge_authorization` and performs no merge

### Requirement: Twitter and wiki-writeback effects preserve destination authority and idempotency
The `twitter_post` adapter SHALL derive the posting account from the authorized destination and reject a payload handle that resolves to a different account. A real post SHALL require soul authority, exact destination consent, credentials, and an atomic receipt reservation; otherwise it SHALL return structured error or dry-run evidence. The `wiki_write_back` adapter SHALL require soul authority, exact destination consent, an explicit idempotency hint, universe context, and a wiki-relative same-universe target; it SHALL append or update the marked result section and SHALL use its receipt to avoid duplicate writes. Neither adapter SHALL raise into the completion path.

#### Scenario: Twitter payload cannot redirect the authorized account
- **WHEN** a Twitter packet's payload handle differs from the account derived from its authorized destination
- **THEN** the adapter returns `handle_authority_mismatch` and performs no post

#### Scenario: Twitter duplicate is idempotent
- **WHEN** a prior successful receipt exists for the derived Twitter idempotency hint
- **THEN** the adapter returns recorded post evidence and does not call the external API again

#### Scenario: Wiki writeback requires an explicit idempotency hint
- **WHEN** an otherwise authorized wiki-writeback packet omits its idempotency hint
- **THEN** the adapter returns a dry run with `reason=missing_idempotency_hint` and leaves the page unchanged

#### Scenario: Wiki writeback stays inside the universe wiki
- **WHEN** a consented packet targets a valid same-universe page and holds a reservation
- **THEN** the adapter appends or updates the marked section and finalizes a receipt with old/new hash evidence

### Requirement: Windows desktop effects require approval, consent, host attestation, and redacted evidence
The host-local Windows desktop adapter SHALL require explicit affirmative user approval in the packet, exact per-universe consent, an attested interactive Windows desktop runtime, and an idempotency reservation before any host action. A missing approval SHALL error, missing consent SHALL dry-run, and a non-Windows or non-interactive runtime SHALL return `no_host_available` before a receipt or action. Duplicate and in-flight reservations SHALL prevent repeat actions. Successful evidence SHALL redact local paths into stable path handles and SHALL not expose protected asset bytes.

#### Scenario: User approval is mandatory
- **WHEN** a Windows desktop packet lacks affirmative user approval or contains negative approval text
- **THEN** the adapter returns `approval_required` before checking consent, reserving a receipt, downloading, or launching anything

#### Scenario: Wrong runtime is refused before action
- **WHEN** approval and consent exist but runtime attestation is not an interactive Windows desktop
- **THEN** the adapter returns `no_host_available` and performs no host-local action

#### Scenario: Successful evidence redacts local paths
- **WHEN** an approved, consented, attested action succeeds
- **THEN** the finalized evidence contains stable path handles rather than private filesystem paths or protected asset bytes
