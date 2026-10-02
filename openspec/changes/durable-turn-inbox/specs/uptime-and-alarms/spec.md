## ADDED Requirements

### Requirement: A Deploy Waits For In-Flight Work Before It Swaps The Daemon
The production deploy SHALL NOT recreate the daemon while work is in flight, except at its cap, when the daemon is not serving, when the in-flight check cannot answer three times running, or when a host-mutating recovery workflow is queued behind it. Work is in flight when an account seat is held by a live holder process (expired or not), or when a queued, running or resumed graph run is owned by a live process. A row with no owner token counts if its run started after the daemon container did. The check (`scripts/turns_in_flight.py`, driven by `deploy/wait_for_turns.sh` from the deploy-prod step "Wait for in-flight turns") SHALL run in a throwaway sibling container that uses the daemon's image and uid, mounts the data volume, has no network, and never execs into the daemon. It SHALL run outside the host-mutation lock. Every remote call SHALL be bounded. The cap SHALL include the image prefetch. While waiting, the deploy SHALL refresh an expiring pending marker that `get_status.deploy_pending` reports.

#### Scenario: A long turn finishes before the swap
- **WHEN** a deploy starts while a chat turn holds an interactive seat
- **THEN** the deploy polls until the seat is released, swaps only then, and the turn's reply reaches the client from the old daemon

#### Scenario: The cap still bounds the wait
- **WHEN** work stays in flight for the whole cap
- **THEN** the deploy proceeds with outcome `cap_reached`, and the cut turn is settled and reported by the startup reconcile

#### Scenario: Recovery is never queued behind a polite wait
- **WHEN** p0-outage-triage, restart-daemon, install-host-services or apply-daemon-env is queued behind the deploy's concurrency group
- **THEN** the wait ends with outcome `yield_to_host_mutation` and the deploy proceeds

#### Scenario: An unverifiable probe is never read as idle
- **WHEN** the probe upload is missing, partial or stale, or the sibling container cannot run
- **THEN** the poll is `unknown`, and only three consecutive unknowns let the deploy proceed (`check_unavailable`)

### Requirement: A Turn Sent During A Deploy Hold Is Queued Durably And Answered Once After The Swap
Once a waiting deploy has set the hold on its pending marker, the `converse` handler SHALL admit no new turn. For an authenticated owner of the resolved universe, it SHALL first persist the message verbatim to the durable turn inbox, record it in the thread with a queued notice, and return that notice as the reply. It SHALL NOT refuse the message. The next boot SHALL replay each queued message once, after orphaned-turn reconciliation, as a served turn of the same owner and thread under authority re-derived at replay. A message whose replay was claimed but never finished SHALL be settled as interrupted with the standard notice and SHALL NOT be run again. An expired marker SHALL mean no hold.

#### Scenario: A message during the hold survives the swap
- **WHEN** the owner sends a message while the hold is set, and the daemon is then recreated
- **THEN** the thread shows the message and the queued notice at once, and after the swap the new daemon answers it in the same thread exactly once

#### Scenario: Authority changed while queued
- **WHEN** the universe is no longer bound to the owner at replay
- **THEN** the queued message is settled `failed` with a failure notice and no turn runs

#### Scenario: A crash during replay never doubles effects
- **WHEN** a boot dies after claiming a queued message and before recording its outcome
- **THEN** the next boot settles it `interrupted` with the interrupted-turn notice and does not run it again

#### Scenario: A dead deploy releases the hold
- **WHEN** the deploy job dies while the hold is set
- **THEN** the marker expires within its TTL, new turns run normally, and the old daemon drains anything queued
