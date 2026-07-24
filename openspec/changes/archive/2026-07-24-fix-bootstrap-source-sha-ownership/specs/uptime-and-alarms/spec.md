## MODIFIED Requirements

### Requirement: Convergent Host Uptime Service Installation
The production host uptime installer SHALL synchronize the five service/timer pairs for `tinyassets-watchdog`, `daemon-watchdog`, `tinyassets-backup`, `tinyassets-prune`, and `tinyassets-disk-watch` plus the exact runtime closure `deploy/{daemon-watchdog.sh,backup.sh}`, `scripts/{__init__,watchdog,mcp_public_canary,disk_watch,disk_autoprune,rotate_run_transcripts,backup_ship_gh,backup_prune}.py`, `tinyassets/__init__.py`, and `tinyassets/storage/{__init__,rotation}.py`. It SHALL install runtime assets into a content-addressed release, make unit execution resolve through one atomic `current` pointer, and give disk-watch the installed working directory required for its module import. After acquiring a bounded-wait lock derived from canonical safe target roots, it SHALL pause timers without killing active services, treat active, activating, reloading, and deactivating services as non-quiescent, fail closed on unreadable or unknown systemd state, wait a bounded interval for oneshots to finish, install the complete manifest, reload systemd, atomically activate the release, enable and start every timer on every invocation, and fail unless every timer is both enabled and active. Fresh-host bootstrap, source-SHA-pinned post-deploy reconciliation, and the restart workflow's install option SHALL invoke this same installer and obtain its exact manifest from that installer. Bootstrap Git operations and source-SHA resolution SHALL converge across the canonical checkout's root-to-service-account ownership transition while every Git process runs as the checkout's current owner; bootstrap SHALL NOT add any safe-directory exception, and SHALL validate a full lowercase commit SHA before invoking the shared installer. Automatic reconciliation SHALL use the triggering workflow's full source SHA; manual and restart dispatches SHALL use and record immutable `github.sha`. Each workflow SHALL verify a checksum in a unique remote staging directory. Bootstrap SHALL provide `sudo`, `visudo`, and `flock`; the installer SHALL validate a private scoped-watchdog sudoers candidate before atomic installation. Same-target installs SHALL wait boundedly and each acquired caller SHALL verify convergence; installs against distinct target roots SHALL remain parallel. Both watchdog timers SHALL remain enabled and active on a fresh host while their services skip recovery until `TINYASSETS_IMAGE` is configured.

#### Scenario: Fresh host receives every uptime layer
- **WHEN** bootstrap runs against a host with none of the uptime units installed
- **THEN** all five timer/unit pairs and the exact runtime closure are installed before systemd reload
- **AND** disk-watch can import transcript rotation from its installed working directory
- **AND** every timer is enabled, active, and explicitly verified
- **AND** watchdog services do not start an intentionally unconfigured daemon

#### Scenario: Repeat install repairs disabled current timers
- **WHEN** every installed file is byte-current but one or more required timers are disabled or inactive
- **THEN** rerunning either installer caller enables and starts every timer instead of skipping activation

#### Scenario: Bootstrap resolves the checkout under its owning identity
- **WHEN** fresh bootstrap reads the root-owned checkout or repeat bootstrap updates and reads the service-account-owned checkout
- **THEN** every Git process runs as the checkout's current owner
- **AND** bootstrap stores a validated full lowercase `HEAD` SHA for the shared installer
- **AND** no safe-directory exception is created

#### Scenario: Installation failure stays visible
- **WHEN** a prerequisite, repository/SHA validation, manifest/checksum validation, sudoers validation, copy, daemon reload, timer activation, enabled check, or active check fails
- **THEN** bootstrap or the installer exits non-zero and does not report convergence

#### Scenario: Active oneshot is not killed or mixed with new files
- **WHEN** a timer service remains active after timers are paused
- **THEN** the installer waits without stopping that service
- **AND** on bounded timeout it restores timer activation and exits before changing installed files

#### Scenario: Workflow installs the triggering source
- **WHEN** host reconciliation follows a successful deploy workflow run
- **THEN** its checkout and checksummed private remote bundle use that triggering run's full source SHA
- **WHEN** reconciliation is manually dispatched
- **THEN** it records, bundles, and installs the dispatch's immutable `github.sha`
- **AND** the restart workflow's install option delegates its `github.sha` bundle to the same installer

#### Scenario: Concurrent targets remain isolated
- **WHEN** at least 64 callers install into distinct resolved target roots concurrently
- **THEN** every target receives only its own manifest and converges independently
- **WHEN** at least 32 callers target the same resolved root within the lock-wait bound
- **THEN** their mutations do not interleave and every caller subsequently verifies convergence
