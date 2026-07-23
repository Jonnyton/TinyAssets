# Uptime and Alarms

> As-built baseline (2026-07-22, change `backfill-uptime-and-alarms`): describes the shipped monitoring, incident paging, bounded recovery, deploy rollback, backup, and disaster-recovery contracts. Known gaps remain non-normative limitations in the archived change design.

## Purpose

Keep the operational uptime control paths explicit and testable without absorbing the MCP protocol, daemon scheduling, or community patch-loop contracts owned by neighboring capabilities.
## Requirements
### Requirement: Host-Independent Public Canary And Incident Lifecycle

The platform SHALL run the Layer-1 public uptime control path on GitHub Actions every five minutes, on manual dispatch, and after every completed `Deploy prod` workflow (`.github/workflows/uptime-canary.yml`). The probe job SHALL run only after a successful deploy completion, while the alarm sink SHALL distinguish the probe result as literal red, literal green, or unknown. The bundle SHALL probe the canonical MCP handshake, a real tool call, daemon last activity, sustained revert-loop state, and the wiki anonymous-write gate plus persisted read. The wiki anonymous-write sub-probe SHALL accept only an HTTP 401 response with a non-empty `WWW-Authenticate` challenge as successful write-gate evidence, then SHALL verify the persisted anonymous `read_page` draft. It SHALL treat every dispatched JSON tool result, a 401 without that challenge, and every other HTTP or network failure as red exit 6. The `live-mcp-connector-surface` capability owns the underlying pre-dispatch challenge protocol; this requirement owns its uptime evidence and workflow diagnostic propagation. It SHALL combine executed sub-probes into one red/green result, open a `p0-outage` issue after two consecutive red runs, append evidence while red, and comment recovery then close the issue only on literal green. An unavailable, empty, or unrecognized current result, including a skipped probe after a failed deploy, SHALL be unknown: the sink SHALL make no label or issue mutation, SHALL not page, and SHALL complete successfully so unknown cannot become red threshold evidence. MCP protocol and handle correctness remain owned by `live-mcp-connector-surface`; this requirement owns probe orchestration and incident state.

#### Scenario: Second consecutive red opens a durable incident

- **WHEN** the combined Layer-1 bundle is red and the prior completed uptime-canary run also failed
- **THEN** the alarm sink opens one GitHub issue labeled `p0-outage` with the probe exit and output
- **AND** subsequent red ticks append evidence to that open issue instead of creating a parallel incident

#### Scenario: Green closes the incident

- **WHEN** the combined Layer-1 bundle is literally green while a `p0-outage` issue is open
- **THEN** the alarm sink appends a `GREEN — RECOVERED` record and closes the issue as completed

#### Scenario: Unknown result preserves incident state

- **WHEN** the probe result is unavailable, empty, or unrecognized, including when a failed `Deploy prod` completion skips the probe job
- **THEN** the alarm sink records an Actions warning and summary without creating or querying labels or issues, without paging, and without failing the canary workflow
- **AND** an open `p0-outage` issue remains open until a literal green result is observed

#### Scenario: Downstream sub-probes respect upstream health

- **WHEN** the MCP handshake or real-tool probe fails
- **THEN** dependent activity, revert-loop, and wiki probes are skipped where they cannot produce meaningful evidence
- **AND** the upstream failure keeps the combined result red

#### Scenario: Wiki write gate observes the OAuth challenge before persisted read proof

- **WHEN** an anonymous `write_page` call receives HTTP 401 with a non-empty `WWW-Authenticate` header
- **THEN** the wiki sub-probe treats the write gate as green and verifies the persisted anonymous `read_page` draft
- **AND** a dispatched JSON result, a 401 without a challenge, or another HTTP or network error produces exit 6 with the captured diagnostic

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

### Requirement: DNS resolution canary reports probe state through a prior-conclusion alarm sink
The system SHALL declare the DNS canary on GitHub-hosted infrastructure with a `*/15 * * * *` schedule, manual dispatch, and a `dns-canary` concurrency group whose `cancel-in-progress` value is false. That setting SHALL preserve an already running job, while GitHub's concurrency controller MAY replace an older pending same-group run when another run queues; neither the declared schedule nor the group SHALL promise actual dispatch latency or one execution per schedule tick. The probe SHALL call `socket.gethostbyname` once for `tinyassets.io` and once for `mcp.tinyassets.io`, report green only when both calls return without error, and report red otherwise. It SHALL NOT claim that the returned address is public, current across all resolvers, or reachable. The probe job SHALL publish its overall result and diagnostics from a tolerated probe step, then a final non-tolerated step SHALL fail if and only if the published overall result is red. The alarm sink, when the workflow executes, SHALL run regardless of probe-job success, consume the published current-run outputs, create the `dns-red` label if absent, open an issue only when the immediately preceding completed workflow run also failed, append later red evidence to an open issue, and comment recovery before closing an open issue on green.

#### Scenario: Both names resolve
- **WHEN** both single-address resolver calls return without error
- **THEN** the probe reports green even though it does not classify or connect to either returned address, and the final propagation step succeeds

#### Scenario: First red does not page
- **WHEN** the probe is red, there is no open `dns-red` issue, and the immediately prior completed workflow run did not fail
- **THEN** the alarm sink records first-red output without opening an issue and the probe job concludes failure after publishing that output

#### Scenario: Consecutive red opens or updates the incident
- **WHEN** the probe is red and either the immediately prior completed run failed or a `dns-red` issue is already open
- **THEN** the sink opens the threshold-crossing issue or appends the new resolver evidence to the existing issue

#### Scenario: Red conclusion becomes threshold evidence
- **WHEN** the tolerated probe step publishes red
- **THEN** the final probe-job step exits non-zero, the current alarm sink still receives the published red output, and the completed workflow exposes failure to the next run

#### Scenario: Green closes an open DNS incident
- **WHEN** the probe is green and a `dns-red` issue is open
- **THEN** the sink comments `GREEN — RECOVERED` evidence and closes the issue as completed

### Requirement: LLM binding canary verifies status presence rather than provider execution
The system SHALL declare the LLM-binding canary on GitHub-hosted infrastructure with a `0 */6 * * *` schedule, manual dispatch, and an `llm-binding-canary` concurrency group whose `cancel-in-progress` value is false. That setting SHALL preserve an already running job, while GitHub's concurrency controller MAY replace an older pending same-group run when another run queues; neither the declared schedule nor the group SHALL promise actual dispatch latency or one execution per schedule tick. When executed, the canary SHALL initialize an MCP session at `https://tinyassets.io/mcp`, call `get_status`, and select `active_host.llm_endpoint_bound` whenever `active_host` is an object containing that key, including when its value is unset; it SHALL use the historical top-level `llm_endpoint_bound` only when the nested key is absent. It SHALL report red when the selected value is `unset`, empty, false, or none. The workflow SHALL NOT require the optional sandbox check and SHALL NOT execute a model request, so green proves only a reported binding. The probe job SHALL publish its overall result and diagnostics from a tolerated probe step, then a final non-tolerated step SHALL fail if and only if the published overall result is red. Its alarm sink SHALL run regardless of probe-job success, consume the published current-run outputs, and use the same first-red, immediately-prior-failed-run threshold, open-issue append, and green-recovery close lifecycle under `llm-binding-red`.

#### Scenario: Reported endpoint is bound
- **WHEN** MCP initialization and `get_status` succeed and the accepted status field contains a non-empty value other than unset, false, or none
- **THEN** the canary reports green without proving that the provider can complete a model call, and the final propagation step succeeds

#### Scenario: Missing binding or probe failure is red
- **WHEN** the status reports an unset binding or the MCP protocol, network, response shape, or tool call fails
- **THEN** the probe returns non-zero and the workflow exposes red to the alarm sink

#### Scenario: Nested unset binding shadows a historical top-level value
- **WHEN** `active_host` contains `llm_endpoint_bound = "unset"` while the top-level field contains a non-empty historical value
- **THEN** the canary selects the nested unset value and reports red

#### Scenario: Two workflow failures open the binding incident
- **WHEN** the current probe is red, no issue is open, and the immediately prior completed workflow run concluded failure
- **THEN** the sink opens an `llm-binding-red` issue with endpoint, exit, output, run, likely-cause, and runbook evidence

#### Scenario: Red conclusion becomes threshold evidence
- **WHEN** the tolerated probe step publishes red
- **THEN** the final probe-job step exits non-zero, the current alarm sink still receives the published red output, and the completed workflow exposes failure to the next run

#### Scenario: Binding recovery closes the incident
- **WHEN** the probe is green and an `llm-binding-red` issue is open
- **THEN** the sink comments recovery evidence and closes the issue as completed

### Requirement: Scheduled release reconciliation uses deploy-run ancestry as its production proxy
The system SHALL declare release reconciliation with a `*/15 * * * *` schedule, manual dispatch, and a `release-reconcile` concurrency group whose `cancel-in-progress` value is false. That setting SHALL preserve an already running job, while GitHub's concurrency controller MAY replace an older pending same-group run when another run queues; neither the declared schedule nor the group SHALL promise actual dispatch latency or one execution per schedule tick. When executed, it SHALL derive the newest release-relevant commit on `main` from the push-path list in `build-image.yml`, falling back to current `HEAD` when that list cannot be read. It SHALL enumerate successful `Deploy prod` workflow runs filtered to `main`; when any returned run `head_sha` contains the release-relevant commit by Git ancestry it SHALL report in sync, otherwise it SHALL dispatch `build-image.yml` on `main`, from which deploy is expected to chain. This current proxy SHALL NOT claim to read the live release receipt or prove that production still serves the returned deploy-run SHA.

#### Scenario: Later successful deploy contains the relevant commit
- **WHEN** a successful main-branch deploy run's `head_sha` is a descendant of the newest release-relevant commit
- **THEN** reconciliation reports no action even when later docs-only commits exist on `main`

#### Scenario: Missing or stale deploy dispatches a build
- **WHEN** no successful main deploy is returned or no returned `head_sha` contains the newest release-relevant commit
- **THEN** reconciliation dispatches `build-image.yml` on `main` and records the drift reason

#### Scenario: Empty release-path history is a no-op
- **WHEN** path extraction succeeds but no commit touching a release path is found
- **THEN** reconciliation reports no release-relevant history and does not dispatch

#### Scenario: Deploy-run metadata can be a false-green proxy
- **WHEN** a successful deploy run's `head_sha` contains the relevant commit but its published live receipt or current production state differs
- **THEN** this reconciler can still report in sync because it does not read either live source

### Requirement: Disk-pressure timer composes alert, rotation, and disposable-host reclamation with a stop-on-error seam
The system SHALL provide a persistent systemd timer definition with five-minute post-boot, one-hour-since-active, and minute-27 calendar triggers plus a 180-second oneshot service sourcing `/etc/tinyassets/env`; the repository artifact alone SHALL NOT claim that a particular host installed or enabled it. The service SHALL declare three sequential commands: disk alerting, run-transcript rotation, and disk auto-prune. Disk alerting SHALL return 1 at or above `DISK_WARN_PCT` (default 80) whether it opens an issue, lacks a token, or runs dry; auto-prune SHALL trigger at or above `DISK_AUTOPRUNE_PCT` (default 85), run Docker system prune and builder prune without volumes plus a best-effort three-day journal vacuum, and treat a completed non-zero cleanup as logged but non-fatal. Because the service commands have no systemd ignore-failure prefix or `SuccessExitStatus=1`, the current unit SHALL NOT promise that rotation or auto-prune runs after disk alerting returns 1.

#### Scenario: Below warning threshold reaches all three commands
- **WHEN** the watched path is below the warning threshold and earlier commands otherwise succeed
- **THEN** disk alerting returns 0 and systemd proceeds to transcript rotation and the auto-prune threshold check

#### Scenario: Pressure alert can stop the cleanup chain
- **WHEN** disk usage is at or above the warning threshold
- **THEN** `disk_watch.py` returns 1 after its issue or warning path
- **AND** the current systemd unit can fail before transcript rotation and auto-prune execute

#### Scenario: Auto-prune reclaims disposable host data without volumes
- **WHEN** execution reaches auto-prune at or above its threshold
- **THEN** it invokes Docker system and builder prune without `--volumes`, then attempts a three-day journal vacuum

#### Scenario: Missing watched path is non-fatal
- **WHEN** disk alerting or auto-prune cannot stat its configured path
- **THEN** that script logs a warning and returns 0 rather than failing the timer solely because the path is absent

### Requirement: Production deploy verifies reported LLM binding and sandbox readiness after public canaries

The production deploy workflow SHALL run `scripts/verify_llm_binding.py` after
the public canaries in both the configured-auth-bundle and no-bundle branches
with `--timeout 20 --require-sandbox --retries 12 --retry-delay 10`. The
verifier SHALL first require a reported LLM binding. When sandbox checking is
enabled, a missing or falsey `sandbox_status.bwrap_available` SHALL raise
`VerifyError` code 5 carrying the reported reason, or
`sandbox_status missing` when no reason is present. The CLI SHALL retry
`VerifyError` failures up to the requested total attempt count and return the
last error code if no attempt recovers.

This post-deploy readiness gate is distinct from the scheduled LLM-binding
canary, which intentionally omits `--require-sandbox`. Neither path executes a
model request, and a green readiness observation is not proof of workload
confinement.

#### Scenario: Missing sandbox readiness produces exit code 5

- **WHEN** the verifier sees a reported LLM binding but missing or falsey `sandbox_status.bwrap_available`
- **THEN** the sandbox check raises `VerifyError` code 5 with the reported reason, or `sandbox_status missing` when no reason is present
- **AND** exhausting the configured attempts returns exit code 5

#### Scenario: A later green observation recovers within the retry budget

- **WHEN** an earlier attempt reports unavailable sandbox readiness and a later attempt reports `bwrap_available=true`
- **THEN** the CLI retries through the configured total-attempt budget
- **AND** returns exit code 0 after the green observation

#### Scenario: Both deploy auth branches require the same readiness evidence

- **WHEN** production deployment reaches post-canary verification with or without a configured Codex auth bundle
- **THEN** the selected branch invokes the verifier with timeout 20, required sandbox readiness, 12 total attempts, and a 10-second retry delay

### Requirement: Executable Uptime Alarm Concurrency Proof

The uptime control path SHALL preserve the global `uptime-canary` concurrency group with `cancel-in-progress: false` and SHALL have an executable proof that runs the exact alarm-sink GitHub-script against shared incident state. The proof SHALL model one running plus one replaceable pending run, execute serialized and coalesced schedules, and prove a single incident across red, unknown, later red, and green observations. It SHALL prove unknown makes no incident mutation, later red appends to the same incident, green closes it, and the actual paging decision sees the shared PAGED marker and produces no duplicate immediate page. The proof artifact SHALL state the command, environment, date, scheduler-model limitation, and result.

#### Scenario: Coalesced uptime ticks preserve one incident and one immediate page

- **WHEN** a red observation opens an incident and overlapping ticks are serialized or coalesced under the global concurrency group
- **THEN** unknown performs no mutation, a later red appends to that same incident, and green closes it
- **AND** the real paging decision treats the shared immediate-page marker as ineligible for another immediate page
