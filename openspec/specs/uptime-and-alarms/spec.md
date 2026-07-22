# Uptime and Alarms

> As-built baseline (2026-07-22, change `backfill-uptime-and-alarms`): describes the shipped monitoring, incident paging, bounded recovery, deploy rollback, backup, and disaster-recovery contracts. Known gaps remain non-normative limitations in the archived change design.

## Purpose

Keep the operational uptime control paths explicit and testable without absorbing the MCP protocol, daemon scheduling, or community patch-loop contracts owned by neighboring capabilities.

## Requirements

### Requirement: Host-Independent Public Canary And Incident Lifecycle

The platform SHALL run the Layer-1 public uptime control path on GitHub Actions every five minutes, on manual dispatch, and after a successful `Deploy prod` completion (`.github/workflows/uptime-canary.yml`). The bundle SHALL probe the canonical MCP handshake, a real tool call, daemon last activity, sustained revert-loop state, and the wiki anonymous-write gate plus persisted read. It SHALL combine the sub-probes into one red/green result, open a `p0-outage` issue after two consecutive red runs, append evidence while red, and comment recovery then close the issue on green. MCP protocol and handle correctness remain owned by `live-mcp-connector-surface`; this requirement owns probe orchestration and incident state.

#### Scenario: Second consecutive red opens a durable incident

- **WHEN** the combined Layer-1 bundle is red and the prior completed uptime-canary run also failed
- **THEN** the alarm sink opens one GitHub issue labeled `p0-outage` with the probe exit and output
- **AND** subsequent red ticks append evidence to that open issue instead of creating a parallel incident

#### Scenario: Green closes the incident

- **WHEN** the combined Layer-1 bundle is green while a `p0-outage` issue is open
- **THEN** the alarm sink appends a `GREEN — RECOVERED` record and closes the issue as completed

#### Scenario: Downstream sub-probes respect upstream health

- **WHEN** the MCP handshake or real-tool probe fails
- **THEN** dependent activity, revert-loop, and wiki probes are skipped where they cannot produce meaningful evidence
- **AND** the upstream failure keeps the combined result red

### Requirement: Durable Acknowledgement-Aware Emergency Paging

The alarm sink SHALL use the open outage issue and its comments as durable Pushover escalation state (`scripts/pushover_page.py`). With Pushover credentials configured, threshold crossing SHALL send a priority-2 emergency page with a 60-second retry interval and 3600-second expiry and record a successful `[PAGED ...]` marker. An unacknowledged open incident SHALL be eligible for fresh pages at the 1-hour, 4-hour, and 24-hour ladder rungs, then no more often than every 24 hours. A non-bot issue comment after the newest marker SHALL count as human acknowledgement and suppress the next page.

#### Scenario: Threshold crossing pages immediately

- **WHEN** the second consecutive red opens the outage issue and Pushover credentials are present
- **THEN** the workflow sends a priority-2 `vibrate` page with retry and expiry values
- **AND** a successful send appends a machine-readable PAGED marker to the issue

#### Scenario: Human acknowledgement suppresses escalation

- **WHEN** a non-bot comment was created after the newest PAGED marker
- **THEN** the next alarm tick returns `host_acknowledged` and does not send another page

#### Scenario: Missing paging state fails visibly

- **WHEN** an incident is page-eligible but credentials are absent or the Pushover POST fails
- **THEN** the paging command returns a non-zero failure and does not emit a false PAGED marker

### Requirement: Layered Bounded Host Recovery

The production host SHALL combine service restart policy with two installed watchdog paths. `tinyassets-daemon.service` SHALL run compose in the foreground with `Restart=always`, a ten-second restart delay, and a five-restart-per-five-minute start limit. `tinyassets-watchdog.timer` SHALL probe the local MCP endpoint every 30 seconds, restart `tinyassets-daemon.service` after three consecutive reds, and suppress repeat restarts for ten minutes. `daemon-watchdog.timer` SHALL run every two minutes under a non-blocking process lock and restart the service when the systemd unit is inactive, the daemon container is stopped, or the freshest worker-supervisor heartbeat is older than 900 seconds. A successful watchdog restart SHALL be followed by a later probe/heartbeat observation rather than treated as proof of recovery by the restart command alone.

#### Scenario: Hung MCP endpoint crosses the probe threshold

- **WHEN** the bootstrap-installed MCP watchdog records three consecutive red local probes and no restart occurred in the prior ten minutes
- **THEN** it issues the narrowly allowed restart of `tinyassets-daemon.service`, resets the red streak optimistically, and records the restart
- **AND** the next timer tick probes again to determine actual recovery

#### Scenario: Dead unit or stale fleet heartbeat restarts once per shell-watchdog run

- **WHEN** the two-minute daemon watchdog finds an inactive unit, a stopped daemon container, or a freshest supervisor heartbeat older than 900 seconds
- **THEN** it restarts `tinyassets-daemon.service` and exits that run
- **AND** overlapping invocations on that watchdog's lock exit without a second restart

#### Scenario: Systemd restart storms are bounded

- **WHEN** the foreground compose service repeatedly exits
- **THEN** systemd waits ten seconds between restarts and stops automatic attempts after five starts inside five minutes until the limit is reset

### Requirement: Class-Specific P0 Triage And Re-Probe

When a `p0-outage` issue is opened, the P0 triage workflow SHALL collect a pre-restart diagnostic bundle, classify it with the priority-ordered `env_unreadable`, `tunnel_token`, `provider_exhaustion`, `disk_full`, `oom`, `image_pull_failure`, `watchdog_hotloop`, or `unknown` class, execute the class-specific bounded response, wait for startup where applicable, and re-probe the canonical MCP URL. Green SHALL close the outage as auto-recovered; persistent red SHALL add `needs-human` with diagnostics. Tunnel-token repair SHALL remain manual, and provider-exhaustion worker pause SHALL remain gated by `TINYASSETS_REVERT_AUTO_REPAIR` while paging regardless of that gate.

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

### Requirement: Digest-Pinned Deploy Admission Rollback And Receipt

The production deploy workflow SHALL resolve the requested image to an immutable digest before mutating production, capture the previous image as a digest-pinned rollback target when possible, verify `/etc/tinyassets/env` remains readable by the daemon user after restart, require the canonical MCP canary and advertised-handle assertion to pass, and only then publish `/data/release-state.json` with source/build/deploy provenance, immutable image identity, config hash, `canary_bundle_status="passed"`, and the prior rollback target. A post-mutation failure with a captured previous image SHALL reinstall that immutable image, restart, and require a rollback canary; deploy failure SHALL open a distinct `deploy-failed` issue.

#### Scenario: Mutable or missing target is rejected before production mutation

- **WHEN** the requested build tag cannot be resolved to a registry digest
- **THEN** the deploy fails before changing `TINYASSETS_IMAGE` or restarting production

#### Scenario: Receipt is published only after admission checks

- **WHEN** the immutable image is running, env readability passes, and the canonical canary plus handle assertion pass
- **THEN** the workflow writes an owned, readable `/data/release-state.json` receipt containing the deployed digest and recorded rollback target

#### Scenario: Failed admitted deploy rolls back and proves recovery

- **WHEN** a failure occurs after the deploy step succeeded and a prior immutable image was captured
- **THEN** the workflow atomically restores that previous image, restarts the daemon, waits, and runs the canonical MCP canary
- **AND** it opens a `deploy-failed` issue whether the failure was in deploy, canary, or rollback handling

### Requirement: Nightly Two-Tier Backup And Manual Fresh-Host Data-Restore Drill

The installed backup timer SHALL run nightly at 03:00 UTC and catch up after a missed schedule. `deploy/backup.sh` SHALL create a strict brain archive using SQLite's backup API for database files and a best-effort live full-volume archive that tolerates only GNU tar's file-changed exit 1; it SHALL upload both tiers to the configured rclone `BACKUP_DEST` and apply per-tier daily/weekly/monthly retention, with optional best-effort GitHub release shipping when `GH_TOKEN` is set. The manually dispatched DR workflow SHALL provision a fresh DigitalOcean Droplet, bootstrap it, transfer a selected full archive from the primary host, restore the data volume without implicitly starting services, start the daemon separately, probe MCP through an SSH port forward, log a pass, and destroy the successful drill host. A red probe SHALL open `dr-failed` and leave the host available by default; a mid-job failure SHALL run cleanup.

#### Scenario: Nightly backup preserves strict brain state and a recoverable full volume

- **WHEN** the persistent 03:00 UTC timer fires
- **THEN** the backup copies top-level SQLite databases transactionally into the brain tier, creates the full live-volume tier, uploads both to `BACKUP_DEST`, and prunes retention
- **AND** a full-tier tar exit of 1 is retained as a hot-volume warning while exit 2 or greater fails the backup

#### Scenario: Restore and start remain separate operations

- **WHEN** the DR workflow restores the selected archive into a fresh host's `tinyassets-data` volume
- **THEN** the restore script exits after extraction without starting the daemon
- **AND** the workflow starts only the daemon service in a separate step before probing it

#### Scenario: Fresh-host drill records success or preserves failure evidence

- **WHEN** the SSH-forwarded MCP probe is green
- **THEN** the workflow appends the backup/run evidence to `docs/ops/dr-drill-log.md` and destroys the drill Droplet
- **WHEN** the probe is red
- **THEN** it opens a `dr-failed` issue and leaves the Droplet running unless `destroy_on_failure` was explicitly selected
