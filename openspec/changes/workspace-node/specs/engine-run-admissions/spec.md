## MODIFIED Requirements

### Requirement: Engine run admissions are charged as writes and settled by what fired

The settlement rule that every sink other than a GET/HEAD `authenticated_external_call` settles a run as a write SHALL have exactly one exception: a `workspace` `checkout` (which is charged as a `workspace` job) SHALL settle the run's external-write admission as a read.
A `workspace` `push` settles as a write; `discard` is a workspace job and
SHALL NOT be classified as a read. All other clauses of this requirement
are unchanged.

#### Scenario: a checkout does not spend the external-write budget
- **WHEN** a run checks out a repository, reads and runs it, and writes nothing externally
- **THEN** its admission settles as `read` and one `workspace` job is charged

## ADDED Requirements

### Requirement: Workspace jobs are admitted and settled through their own ledger kind with the maximum charge reserved before the wire

The engine SHALL admit every `workspace` operation (`checkout`, `push`, `discard`, provisioning) as kind `workspace` in the per-universe rolling ledger, bounded by jobs per hour (default 10) and bytes per hour (default 20 GiB), both tier-raisable, SHALL reserve the operation's maximum byte charge in the admission transaction before any network activity — the lease bound for a checkout, the bounded bundle size for a push, the cache cap for provisioning — SHALL reconcile the reservation downward to measured bytes afterwards, keeping the maximum for an unknown or interrupted transfer, and SHALL name the exhausted bound in a refusal.
Workspace git transfers and provisioning downloads SHALL be charged to this
ledger and SHALL NOT be charged to the HTTP usage budgets of change
`run-usage-budgets` (500 dispatches / 256 MiB per root run, 5,000 / 2 GiB
per universe-hour), which bound `authenticated_external_call` only.

#### Scenario: the hourly workspace bytes are exhausted
- **WHEN** a universe's checkouts in the rolling hour have reserved 20 GiB
- **THEN** the next `checkout` is refused as `workspace_quota_exceeded`, naming the bytes bound and when it clears, before any bytes move

#### Scenario: two concurrent checkouts cannot together cross the hourly bound
- **WHEN** two checkouts are admitted concurrently with 5 GiB of the hourly bytes left and 4 GiB lease bounds
- **THEN** exactly one reserves and the other is refused; a crash before reconciliation leaves the first's full reservation charged

#### Scenario: a large checkout is not an HTTP budget event
- **WHEN** a run checks out a 3 GiB repository
- **THEN** the run's HTTP byte budget is unchanged and the workspace ledger records the bytes
