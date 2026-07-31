## MODIFIED Requirements

### Requirement: OpenSpec drain merge progress is canonical and replay-safe

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
suppress that target within the bounded run, and continue candidate discovery.
Malformed, unverifiable, or not-yet-consumed merge results MUST remain on their
existing fail-closed paths.

#### Scenario: Consumed merge replay is suppressed without false progress

- **GIVEN** a bounded run has already consumed a canonical verified merge
  receipt for a target
- **WHEN** a later valid worker result reports the same canonical receipt
- **THEN** completed-slice and merge-receipt counts remain unchanged
- **AND** the stale admission and resume target are cleared
- **AND** the target is excluded from the run's next candidate discovery
- **AND** the consecutive failure budget is not charged

#### Scenario: Unverified merge does not use replay suppression

- **WHEN** a merge result is malformed, unverifiable, or is not already in the
  run's consumed receipt set
- **THEN** the supervisor follows the existing validation and failure policy
- **AND** does not suppress it as an already-consumed replay
