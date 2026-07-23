## MODIFIED Requirements

### Requirement: Class-Specific P0 Triage And Re-Probe

When a `p0-outage` issue is opened, the P0 triage workflow SHALL collect a pre-restart diagnostic bundle, classify it with the priority-ordered `env_unreadable`, `tunnel_token`, `provider_exhaustion`, `disk_full`, `oom`, `image_pull_failure`, `watchdog_hotloop`, or `unknown` class, execute the class-specific bounded response, wait for startup where applicable, and re-probe the canonical MCP URL. A bounded class-specific repair, generic restart, or provider-exhaustion page failure SHALL remain visible but SHALL NOT prevent the canonical re-probe. Green SHALL close the outage only when that re-probe is green; persistent red SHALL add `needs-human` with diagnostics and fail the triage run visibly. Tunnel-token repair SHALL remain manual, and provider-exhaustion worker pause SHALL remain gated by `TINYASSETS_REVERT_AUTO_REPAIR` while the existing `scripts/pushover_page.py` CLI pages regardless of that gate. The workflow SHALL preserve issue-scoped concurrency with in-progress runs not cancelled.

#### Scenario: Environment permission regression is repaired before restart

- **WHEN** diagnostics contain the canonical `ENV-UNREADABLE` marker
- **THEN** triage restores `/etc/tinyassets/env` to `root:tinyassets` mode `0640`, verifies the daemon user can read it, performs the generic compose recreate, and re-probes

#### Scenario: Image pull failure uses only the recorded immutable rollback target

- **WHEN** diagnostics classify as `image_pull_failure`
- **THEN** triage reads `rollback_target` from `/data/release-state.json`, requires an `@sha256:` reference, atomically installs it as `TINYASSETS_IMAGE`, pulls it, and restarts the service
- **AND** absence of a digest-pinned target fails the repair instead of falling back to a mutable image tag

#### Scenario: Manual and gated classes remain honest

- **WHEN** diagnostics classify as `tunnel_token`
- **THEN** automation opens distinct rotation work and pages rather than claiming an automatic token repair
- **WHEN** diagnostics classify as `provider_exhaustion` while its auto-repair variable is not enabled
- **THEN** automation pages in warn-only mode and does not stop the worker or create pause sentinels

#### Scenario: Failed bounded repair still reaches the canonical decision

- **WHEN** a class-specific repair or generic restart exits non-zero
- **THEN** its failure remains visible and the workflow continues to canonical re-probe
- **AND** only a green re-probe closes the issue while a red re-probe adds `needs-human` and fails the run visibly

#### Scenario: Provider page failure stays visible but does not replace probe truth

- **WHEN** the provider-exhaustion page command exits non-zero
- **THEN** the page step is visibly failed while canonical re-probe still runs
- **AND** only that re-probe determines auto-recovery or persistent-red escalation

## ADDED Requirements

### Requirement: Executable Uptime Alarm Concurrency Proof

The uptime control path SHALL preserve the global `uptime-canary` concurrency group with `cancel-in-progress: false` and SHALL have an executable proof that runs the exact alarm-sink GitHub-script against shared incident state. The proof SHALL model one running plus one replaceable pending run, execute serialized and coalesced schedules, and prove a single incident across red, unknown, later red, and green observations. It SHALL prove unknown makes no incident mutation, later red appends to the same incident, green closes it, and the actual paging decision sees the shared PAGED marker and produces no duplicate immediate page. The proof artifact SHALL state the command, environment, date, scheduler-model limitation, and result.

#### Scenario: Coalesced uptime ticks preserve one incident and one immediate page

- **WHEN** a red observation opens an incident and overlapping ticks are serialized or coalesced under the global concurrency group
- **THEN** unknown performs no mutation, a later red appends to that same incident, and green closes it
- **AND** the real paging decision treats the shared immediate-page marker as ineligible for another immediate page
