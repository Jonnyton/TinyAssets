## ADDED Requirements

### Requirement: A Deploy Waits For In-Flight Work Before It Swaps The Daemon
The production deploy SHALL NOT recreate the daemon while work is in flight. Work is in flight when an account seat is held by a live holder process (expired or not), or when a queued, running or resumed graph run is owned by a live process; a row with no owner token counts if its run started after the daemon container did. Only four conditions let the deploy proceed while work is in flight: its cap, a daemon that is not serving, three consecutive unanswerable checks, or a host-mutating recovery workflow queued behind it. The check (`scripts/turns_in_flight.py`, driven by `deploy/wait_for_turns.sh` from the deploy-prod step "Wait for in-flight turns") SHALL run in a throwaway sibling container. That container uses the daemon's image and uid, mounts the data volume, has no network, and never execs into the daemon. The check SHALL run outside the host-mutation lock, bound every remote call, include the image prefetch in its cap, and refresh an expiring pending marker that `get_status.deploy_pending` reports.

#### Scenario: A long turn finishes before the swap
- **WHEN** a deploy starts while a chat turn holds an interactive seat
- **THEN** the deploy polls until the seat is released, swaps only then, and the turn's reply reaches the client from the old daemon

#### Scenario: Recovery is never queued behind a polite wait
- **WHEN** p0-outage-triage, restart-daemon, install-host-services or apply-daemon-env is queued behind the deploy's concurrency group
- **THEN** the wait ends with outcome `yield_to_host_mutation` and the deploy proceeds

#### Scenario: An unverifiable probe is never read as idle
- **WHEN** the probe upload is missing, partial or stale, or the sibling container cannot run
- **THEN** the poll is unknown, and only three consecutive unknowns let the deploy proceed

### Requirement: A Deploy Hands Over The Owner Or Touches Frontends Only, And Measures Both
A deploy whose changes touch only frontend modules SHALL replace frontends blue-green and SHALL NOT touch the execution owner. A deploy that touches owner code SHALL hand the owner over in five steps:
1. start the new owner in standby;
2. close the old owner's admission;
3. drain in-flight turns up to the owner drain bound;
4. release the lease;
5. let the new owner acquire, run the barrier, reconcile, and then open admission.

Each deploy SHALL report failed requests and interrupted turns.

#### Scenario: A frontend-only deploy interrupts nothing
- **WHEN** a merge changes only frontend modules while a long turn runs
- **THEN** the turn keeps running in the owner, and the deploy reports zero failed requests and zero interrupted turns

#### Scenario: An owner deploy reports what it cut
- **WHEN** a turn is still running at the owner drain bound
- **THEN** it is reconciled into a held state with the interrupted notice, never replayed, and the deploy reports it as interrupted
