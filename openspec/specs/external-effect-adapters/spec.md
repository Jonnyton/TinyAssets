# External Effect Adapters

> As-built baseline (2026-07-22, change `backfill-independent-shipped-contracts`): describes shipped local completion-path adapter behavior and current limitations. Shared authority, consent, and receipt semantics remain owned by `external-effect-receipts`.

## Purpose

The shipped Branch-completion effect dispatch, sink-specific adapter behavior, system-authored evidence, and current partial-write/finalization boundaries.

## Requirements

### Requirement: Declared node effects dispatch after run completion without changing terminal success
After a normal or resumed Branch run completes, the runtime SHALL inspect each node's declared `effects`, find matching packets only in that node's declared output keys, and dispatch the registered sink adapter. Returned per-node, per-sink evidence SHALL be stored in system-authored `external_write_results`; only evidence with a truthy `error` SHALL also be flattened into `external_write_errors`, so dry-run refusals remain results rather than errors. Per-sink exceptions SHALL become structured crash evidence and SHALL NOT reverse the completed run status. As-built limitation: a top-level effector import or dispatch exception is logged and returns an empty evidence map, so that failure is not persisted as structured run evidence. Nodes without declared effects SHALL produce no adapter work.

#### Scenario: Declared sink receives its matching packet
- **WHEN** a completed node declares a supported effect and one declared output key contains that sink's packet
- **THEN** the runtime dispatches that adapter and records its result under the node and sink in `external_write_results`

#### Scenario: Adapter error does not fail the run
- **WHEN** a sink adapter returns evidence with a truthy `error` or raises inside per-sink dispatch
- **THEN** the runtime records result and flattened error evidence and the Branch run remains completed

#### Scenario: Dry-run refusal is not flattened as an error
- **WHEN** an adapter returns dry-run evidence without an `error` field
- **THEN** the evidence remains in `external_write_results` and no corresponding `external_write_errors` row is created

#### Scenario: Top-level dispatch crash loses structured evidence
- **WHEN** the effector module import or top-level dispatch raises
- **THEN** the runtime logs the exception, returns an empty evidence map, and still completes the Branch run without persisted adapter evidence

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

### Requirement: GitHub pull-request effects apply destination gates and optional-hint receipts
The `github_pull_request` adapter SHALL parse only a matching packet from declared output keys. If no matching packet exists, it SHALL return `error_kind=no_matching_packet` before evaluating the operator kill switch. After a matching packet is found, a truthy `TINYASSETS_EXTERNAL_WRITE_DRY_RUN` operator kill switch SHALL take precedence over destination validation, soul authority, capability, consent, receipt, and external-write work; it SHALL return Phase-2 `operator_kill_switch_active` dry-run evidence preserving the intent and matched output key without invoking GitHub or reserving a receipt. When that kill switch is not active, a packet whose destination is absent, blank, or non-string SHALL remain on the Phase-1 dry-run compatibility path. For a destination-bearing packet, a soul-authority resolver result of denied — from a declared non-match or a soul-read failure — SHALL dry-run, while undeclared authority SHALL fall through to the legacy gates owned by `external-effect-receipts`. A real write SHALL require an exact destination capability and consent; a bound vault credential SHALL outrank environment-vended credentials and SHALL never be returned in Branch-visible evidence. A non-empty caller hint SHALL use the shared atomic receipt lifecycle, but an omitted hint SHALL proceed unreceipted. The adapter SHALL materialize blobs, tree, commit, and head ref before opening the PR, so a later failure can leave partial remote branch state. A successful external write whose receipt finalization fails SHALL still return success evidence marked `receipt_finalize_failed`.

#### Scenario: Operator kill switch precedes missing-destination compatibility
- **WHEN** a matching packet omits its destination while `TINYASSETS_EXTERNAL_WRITE_DRY_RUN` is truthy
- **THEN** the adapter returns Phase-2 dry-run evidence with `reason=operator_kill_switch_active` rather than the Phase-1 missing-destination evidence, without invoking GitHub or reserving a receipt

#### Scenario: Missing packet precedes the operator kill switch
- **WHEN** no declared output contains a matching packet while `TINYASSETS_EXTERNAL_WRITE_DRY_RUN` is truthy
- **THEN** the adapter returns `error_kind=no_matching_packet` rather than manufacturing kill-switch intent evidence

#### Scenario: Missing consent remains a dry run
- **WHEN** a valid destination packet has a credential but no active consent row
- **THEN** the adapter returns destination-specific dry-run evidence and performs no GitHub write

#### Scenario: Concurrent reservation prevents duplicate PRs
- **WHEN** a non-empty hint is supplied and another run holds the same idempotency reservation
- **THEN** the adapter returns `reason=concurrent_in_flight` without invoking PR creation

#### Scenario: Successful duplicate returns recorded evidence
- **WHEN** the idempotency receipt already records a successful PR
- **THEN** the adapter returns a dedup hit with that evidence and performs no external write

#### Scenario: Missing hint opts out of receipts
- **WHEN** an otherwise authorized destination packet omits its idempotency hint
- **THEN** the adapter may materialize the branch and create the PR without reserving or finalizing a receipt

#### Scenario: PR failure can leave materialized branch state
- **WHEN** remote branch materialization succeeds but PR creation fails
- **THEN** the adapter returns failure evidence and releases any receipt reservation without deleting the already-created remote objects or ref

### Requirement: GitHub merge effects bind packet-declared mode to exact head SHA and delegate policy enforcement
The `github_merge` adapter SHALL require a valid repository destination, positive PR number, one of `merge`, `squash`, or `rebase`, packet-supplied authorization mode `github_branch_protection`, a destination capability, and a 40-character expected head SHA. It SHALL fetch the current PR, require it to be open and non-draft, and reject a mismatched head before calling the merge endpoint; wiki positions SHALL be audit context only and SHALL NOT supply the required mode string. The adapter does not query branch-protection configuration, status checks, or reviews itself; it delegates those controls to GitHub's merge endpoint and treats API refusal as structured failure.

#### Scenario: Expected head mismatch refuses stale authorization
- **WHEN** the current PR head differs from the packet's expected head SHA
- **THEN** the adapter returns a stale-authorization error and does not call the merge endpoint

#### Scenario: GitHub API accepts a bound merge
- **WHEN** destination capability is present, the packet names the required mode, the PR is open and non-draft, the expected head matches, and GitHub's merge endpoint accepts the request
- **THEN** the adapter returns merge evidence without independently proving which repository protection, check, or review rules GitHub enforced

#### Scenario: Wiki position cannot authorize merge
- **WHEN** a packet supplies review context but omits `github_branch_protection` authorization
- **THEN** the adapter returns `missing_merge_authorization` and performs no merge

### Requirement: Twitter effects preserve destination binding with transitional authority and optional receipts
The `twitter_post` adapter SHALL derive the posting account from the destination and reject a payload handle that resolves to a different account. A soul-authority resolver result of denied — from a declared non-match or a soul-read failure — SHALL dry-run, while undeclared authority SHALL fall through to exact destination consent and credential gates. The adapter SHALL accept a non-empty caller hint or deterministically derive a SHA-256 hint from source run id, sink, handle, and text, then use the shared receipt lifecycle. A successful post whose receipt finalization fails SHALL remain successful evidence marked `receipt_finalize_failed` and SHALL not be rolled back.

#### Scenario: Twitter payload cannot redirect the authorized account
- **WHEN** a Twitter packet's payload handle differs from the account derived from its authorized destination
- **THEN** the adapter returns `handle_authority_mismatch` and performs no post

#### Scenario: Twitter duplicate is idempotent
- **WHEN** a prior successful receipt exists for the derived Twitter idempotency hint
- **THEN** the adapter returns recorded post evidence and does not call the external API again

#### Scenario: Undeclared soul falls through
- **WHEN** the universe declares no effect-authority grants for the Twitter destination
- **THEN** the adapter continues to exact consent and credential gates rather than requiring a soul grant

### Requirement: Wiki writeback requires a hint but retains transitional authority and best-effort finalization
The `wiki_write_back` adapter SHALL reject a soul-authority resolver result of denied — from a declared non-match or a soul-read failure — while undeclared authority SHALL fall through to exact destination consent. It SHALL require a non-empty idempotency hint, universe context, and an existing same-universe `.md` file under `pages/` or `drafts/`, with at least one subdirectory and no empty, dot, or traversal segments, before reserving a shared receipt. It SHALL append or update the marked result section. If the page write succeeds but receipt finalization fails, the adapter SHALL return successful evidence marked `receipt_finalize_failed`; it SHALL not undo the page write.

#### Scenario: Wiki writeback requires an explicit idempotency hint
- **WHEN** an otherwise authorized wiki-writeback packet omits its idempotency hint
- **THEN** the adapter returns a dry run with `reason=missing_idempotency_hint` and leaves the page unchanged

#### Scenario: Wiki writeback stays inside the universe wiki
- **WHEN** a consented packet targets a valid same-universe page and holds a reservation
- **THEN** the adapter appends or updates the marked section, reports old/new hash evidence, and attempts receipt finalization; a failed finalization adds `receipt_finalize_failed` without undoing the page write

### Requirement: Windows desktop effects gate host actions but provide only narrow evidence redaction
The host-local Windows desktop adapter SHALL require explicit affirmative user approval in the packet, exact per-universe consent, and an attested interactive Windows desktop runtime before any host action. A missing approval SHALL error, missing consent SHALL dry-run, and a non-Windows or non-interactive runtime SHALL return `no_host_available` before a receipt or action. A non-empty idempotency key SHALL use shared duplicate/in-flight reservation handling, while an omitted key SHALL proceed unreceipted. The default action runner SHALL return stable handles for action paths, but evidence redaction only drops four exact path-named keys and converts actual `Path` objects. Auto-generated runtime attestation SHALL contain the raw home-directory string; an injected attestation is appended unchanged and may omit it. The sanitizer SHALL NOT be treated as a general string-path or protected-byte confidentiality boundary. A successful action whose receipt finalization fails SHALL remain successful evidence marked `receipt_finalize_failed`.

#### Scenario: User approval is mandatory
- **WHEN** a Windows desktop packet lacks affirmative user approval or contains negative approval text
- **THEN** the adapter returns `approval_required` before checking consent, reserving a receipt, downloading, or launching anything

#### Scenario: Wrong runtime is refused before action
- **WHEN** approval and consent exist but runtime attestation is not an interactive Windows desktop
- **THEN** the adapter returns `no_host_available` and performs no host-local action

#### Scenario: Default action paths use handles but attestation retains home
- **WHEN** an approved, consented action succeeds using the default action runner and auto-generated runtime attestation
- **THEN** action receipts use stable path handles while the appended runtime attestation still contains its raw `home` string

#### Scenario: Missing idempotency key permits an unreceipted action
- **WHEN** all host gates pass but the packet has no idempotency key
- **THEN** the adapter runs the action without a receipt reservation or exactly-once claim
