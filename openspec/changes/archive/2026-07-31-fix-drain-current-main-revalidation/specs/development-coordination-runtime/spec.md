## MODIFIED Requirements

### Requirement: OpenSpec Drain Proves Work Exhaustion Before Idling

The OpenSpec drain supervisor SHALL accept `NO_CANDIDATE` only when the
canonical claim checker reports zero claimable rows, zero policy-qualified
stale-claim candidates, and zero in-flight rows owned by the drain's exact
identity on freshly fetched `origin/main`. Pre-dispatch admission and
post-result revalidation MUST classify that same explicit current-main ref and
MUST NOT read coordination state from a stale local or detached checkout.

#### Scenario: Detached controller state disagrees with current main

- **WHEN** a worker returns `NO_CANDIDATE`
- **AND** the controller checkout contains a stale local claim that is absent
  from freshly fetched `origin/main`
- **THEN** post-result validation classifies `origin/main`
- **AND** the stale local-only row does not consume a failure strike

#### Scenario: Current main still contains work

- **WHEN** freshly fetched `origin/main` contains claimable, policy-qualified
  stale, or exact-identity-owned work
- **THEN** `NO_CANDIDATE` remains rejected

### Requirement: Drain Watchdog Preserves Identity Across Abrupt Shutdown

The drain watchdog SHALL attach to a live unfinished drain, SHALL resume an
unfinished drain whose recorded controller is dead using the same run directory
and exact identity, and SHALL start a fresh bounded run only when no unfinished
run exists or an explicit restart request has gracefully stopped the prior run.
It MUST NOT automatically restart fatal or failure-budget terminal outcomes.

#### Scenario: Existing manual drain is alive

- **WHEN** the watchdog starts while an unfinished drain lock belongs to a live
  controller
- **THEN** it attaches to that run for health monitoring
- **AND** it does not dispatch another worker

#### Scenario: Computer was shut down abruptly

- **WHEN** the newest drain has no `ended_at` and its recorded controller PID is
  dead
- **THEN** the watchdog resumes that run with stale-lock recovery
- **AND** replacement workers retain the original drain identity

#### Scenario: Previous run failed terminally

- **WHEN** the latest completed run ended at its failure budget or a fatal peer
  error
- **THEN** the watchdog reports down
- **AND** it waits for an explicit restart request instead of spending more
  subscription calls

#### Scenario: Explicit restart gracefully stops a live supervisor

- **WHEN** an explicit restart is requested while a supervisor is live
- **AND** that supervisor exits with a terminal outcome during graceful stop
- **THEN** the watchdog preserves the already-authorized fresh-run decision
- **AND** it starts exactly one fresh bounded supervisor run

#### Scenario: Clean budget ends during the signed-in session

- **WHEN** a supervisor ends at its runtime or slice budget while the watchdog
  remains active
- **THEN** the watchdog may start a new finite supervisor run
- **AND** it still runs only one worker at a time
