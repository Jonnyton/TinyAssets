## MODIFIED Requirements

### Requirement: Verified merge receipts are idempotent per run

The OpenSpec drain supervisor SHALL advance completed-slice progress at most
once for a canonical verified merged pull-request identity. Owner and
repository casing plus numeric formatting of the pull-request number MUST NOT
create a distinct identity. It MUST persist every successful receipt for the
bounded run and reconstruct canonical verified receipts only for legacy result
artifacts whose supervisor audit records successful merge consumption. Result
text or current merge state alone MUST NOT turn a previously failed
verification into a consumed receipt. `PARTIAL` SHALL NOT consume the merge
receipt because later foldback may legitimately return `MERGED` for the same
pull request.

When a valid worker result reports a canonical `MERGED` receipt already
consumed by the same bounded run, the supervisor MUST NOT advance progress,
retry the same admission, or charge the worker failure budget. It SHALL retain
the duplicate audit result, clear the stale admission and resume target,
suppress that target for the remainder of the bounded run across `OWNED`,
`CLAIMABLE`, and `STALE` classifications, and continue candidate discovery.
Malformed, unverifiable, or not-yet-consumed merge results MUST remain on their
existing fail-closed paths.

#### Scenario: Worker replays an already consumed merged PR

- **WHEN** a worker returns `MERGED` with a canonical PR identity already
  present in the run's verified merge receipts
- **THEN** the controller records `INVALID_DUPLICATE_MERGE`
- **AND** does not advance completed slices or merge-receipt counts
- **AND** clears the stale admission and resume target
- **AND** excludes the target from later discovery for this bounded run
- **AND** does not charge the consecutive failure budget

#### Scenario: Legacy run resumes after merged work

- **WHEN** run state predates the merge-receipt field
- **THEN** the controller reconstructs the complete run-bounded unique
  canonical receipt set from successfully consumed result artifacts and their
  supervisor audit records
- **AND** trusts only PRs that still pass controller merge verification

#### Scenario: Legacy merge succeeded through restart recovery

- **WHEN** a pre-receipt run audit records recovered or replayed `MERGED`
  results and the completed-slice ledger unambiguously accounts for every
  recovery candidate
- **THEN** the controller reconstructs and verifies its canonical receipt
- **AND** if the ledger proves how many recoveries succeeded but not which PRs
  succeeded, the controller reconstructs none of the ambiguous receipts and
  permits a retry

#### Scenario: Previously failed merge verification later becomes merged

- **WHEN** a consumed legacy result reported `MERGED` but its supervisor audit
  records `merge-verification-failed`
- **THEN** receipt reconstruction does not consume that PR
- **AND** a later verified `MERGED` retry may advance one slice

#### Scenario: Partial foldback later completes

- **WHEN** a verified `PARTIAL` result is followed by `MERGED` for the same PR
  after foldback
- **THEN** the `MERGED` result may advance one slice because `PARTIAL` did not
  consume its receipt

#### Scenario: Unverified merge does not use replay suppression

- **WHEN** a merge result is malformed, unverifiable, or is not already in the
  run's consumed receipt set
- **THEN** the supervisor follows the existing validation and failure policy
- **AND** does not suppress it as an already-consumed replay
