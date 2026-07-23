## MODIFIED Requirements

### Requirement: GitHub pull-request effects apply destination gates and optional-hint receipts
The `github_pull_request` adapter SHALL parse only a matching packet from declared output keys. After a matching packet is found, a truthy `TINYASSETS_EXTERNAL_WRITE_DRY_RUN` operator kill switch SHALL take precedence over destination validation and return Phase-2 `operator_kill_switch_active` dry-run evidence. When that kill switch is not active, a packet without a destination SHALL remain on the Phase-1 dry-run compatibility path. For a destination-bearing packet, a soul-authority resolver result of denied — from a declared non-match or a soul-read failure — SHALL dry-run, while undeclared authority SHALL fall through to the legacy gates owned by `external-effect-receipts`. A real write SHALL require an exact destination capability and consent; a bound vault credential SHALL outrank environment-vended credentials and SHALL never be returned in Branch-visible evidence. A non-empty caller hint SHALL use the shared atomic receipt lifecycle, but an omitted hint SHALL proceed unreceipted. The adapter SHALL materialize blobs, tree, commit, and head ref before opening the PR, so a later failure can leave partial remote branch state. A successful external write whose receipt finalization fails SHALL still return success evidence marked `receipt_finalize_failed`.

#### Scenario: Operator kill switch precedes missing-destination compatibility
- **WHEN** a matching packet omits its destination while `TINYASSETS_EXTERNAL_WRITE_DRY_RUN` is truthy
- **THEN** the adapter returns Phase-2 dry-run evidence with `reason=operator_kill_switch_active` rather than the Phase-1 missing-destination evidence

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
