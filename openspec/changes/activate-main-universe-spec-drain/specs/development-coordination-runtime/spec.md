## ADDED Requirements

### Requirement: Pre-existing refinery ownership does not exhaust the temporary drain
Until single-active cloud cutover, the OpenSpec drain supervisor SHALL treat an exact assigned refinery target that is proven owned by a pre-existing open pull request as unavailable for the bounded run rather than as a failed delivery attempt. Ownership proof MUST bind the exact current repository and the assigned target to an open PR branch whose creation predates the run; worker prose or an unrelated older PR is insufficient. The refinery worker MUST report that exact PR URL in its terminal marker. The supervisor MUST suppress only that target, MUST preserve every suppressed target for the entire bounded run, MUST immediately continue to another eligible candidate, and MUST NOT record a completed slice, merge receipt, or failure strike. The exact refinery assignment MUST be persisted before dispatch so crash recovery can apply the same target and fresh pull-request checks before consuming an unrecorded result. Missing, malformed, unrelated, non-open, same-run, or unqueryable pull-request evidence MUST be consumed through ordinary fail-closed failure-budget accounting, including during crash recovery.

#### Scenario: Older open PR owns the assigned refinery target
- **WHEN** an assigned refinery worker reports `FAILED` with the exact pull request whose head branch names that assigned target, is still open in the exact repository, and predates the bounded run
- **THEN** the supervisor excludes that target for the rest of the run and immediately considers the next eligible candidate
- **AND** it records no completed slice, merge receipt, or failure strike

#### Scenario: Controller restarts after the refinery result is written
- **WHEN** the exact refinery assignment and a matching unconsumed `FAILED` result survive a controller crash
- **THEN** recovery rechecks the pull request's current open state, exact repository, and pre-run creation time before suppressing the target
- **AND** failed verification consumes the persisted `FAILED` result through ordinary failure-budget accounting before any new dispatch

#### Scenario: Reported PR does not prove pre-existing live ownership
- **WHEN** the reported pull request is unavailable, unrelated to the assigned target, closed, merged, malformed, or created during the bounded run
- **THEN** the supervisor preserves the refinery `FAILED` result and ordinary failure-budget accounting
