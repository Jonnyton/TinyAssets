## ADDED Requirements

### Requirement: DNS resolution canary uses host-independent consecutive-red issue state
The system SHALL declare the DNS canary on GitHub-hosted infrastructure with a `*/15 * * * *` schedule, manual dispatch, and one non-cancelling `dns-canary` concurrency group. The declared schedule SHALL NOT promise actual GitHub dispatch latency. The probe SHALL call `socket.gethostbyname` once for `tinyassets.io` and once for `mcp.tinyassets.io`, report green only when both calls return without error, and report red otherwise. It SHALL NOT claim that the returned address is public, current across all resolvers, or reachable. The alarm sink, when the workflow executes, SHALL run regardless of probe success, create the `dns-red` label if absent, open an issue only when the immediately preceding completed workflow run also failed, append later red evidence to an open issue, and comment recovery before closing an open issue on green.

#### Scenario: Both names resolve
- **WHEN** both single-address resolver calls return without error
- **THEN** the probe reports green even though it does not classify or connect to either returned address

#### Scenario: First red does not page
- **WHEN** the probe is red, there is no open `dns-red` issue, and the immediately prior completed workflow run did not fail
- **THEN** the alarm sink records first-red output without opening an issue

#### Scenario: Consecutive red opens or updates the incident
- **WHEN** the probe is red and either the immediately prior completed run failed or a `dns-red` issue is already open
- **THEN** the sink opens the threshold-crossing issue or appends the new resolver evidence to the existing issue

#### Scenario: Green closes an open DNS incident
- **WHEN** the probe is green and a `dns-red` issue is open
- **THEN** the sink comments `GREEN — RECOVERED` evidence and closes the issue as completed

### Requirement: LLM binding canary verifies status presence rather than provider execution
The system SHALL declare the LLM-binding canary on GitHub-hosted infrastructure with a `0 */6 * * *` schedule, manual dispatch, and one non-cancelling `llm-binding-canary` concurrency group. The declared schedule SHALL NOT promise actual GitHub dispatch latency. When executed, it SHALL initialize an MCP session at `https://tinyassets.io/mcp`, call `get_status`, and report red unless `active_host.llm_endpoint_bound` or the historical top-level `llm_endpoint_bound` is present and not `unset`, empty, false, or none. The workflow SHALL NOT require the optional sandbox check and SHALL NOT execute a model request, so green proves only a reported binding. Its alarm sink SHALL use the same first-red, immediately-prior-failed-run threshold, open-issue append, and green-recovery close lifecycle under `llm-binding-red`.

#### Scenario: Reported endpoint is bound
- **WHEN** MCP initialization and `get_status` succeed and the accepted status field contains a non-empty value other than unset, false, or none
- **THEN** the canary reports green without proving that the provider can complete a model call

#### Scenario: Missing binding or probe failure is red
- **WHEN** the status reports an unset binding or the MCP protocol, network, response shape, or tool call fails
- **THEN** the probe returns non-zero and the workflow exposes red to the alarm sink

#### Scenario: Two workflow failures open the binding incident
- **WHEN** the current probe is red, no issue is open, and the immediately prior completed workflow run concluded failure
- **THEN** the sink opens an `llm-binding-red` issue with endpoint, exit, output, run, likely-cause, and runbook evidence

#### Scenario: Binding recovery closes the incident
- **WHEN** the probe is green and an `llm-binding-red` issue is open
- **THEN** the sink comments recovery evidence and closes the issue as completed

### Requirement: Scheduled release reconciliation uses deploy-run ancestry as its production proxy
The system SHALL declare release reconciliation with a `*/15 * * * *` schedule, manual dispatch, and one non-cancelling `release-reconcile` concurrency group. The declared schedule SHALL NOT promise actual GitHub dispatch latency. When executed, it SHALL derive the newest release-relevant commit on `main` from the push-path list in `build-image.yml`, falling back to current `HEAD` when that list cannot be read. It SHALL enumerate successful `Deploy prod` workflow runs filtered to `main`; when any returned run `head_sha` contains the release-relevant commit by Git ancestry it SHALL report in sync, otherwise it SHALL dispatch `build-image.yml` on `main`, from which deploy is expected to chain. This current proxy SHALL NOT claim to read the live release receipt or prove that production still serves the returned deploy-run SHA.

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
