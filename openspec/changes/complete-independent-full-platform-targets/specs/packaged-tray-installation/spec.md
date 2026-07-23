## ADDED Requirements

### Requirement: Supported desktop platforms receive native verifiable installers
The release system SHALL publish a Windows installer, a notarized macOS application image or package, and both a Debian-family package plus a broadly runnable Linux application artifact. Each artifact SHALL identify product version, source commit, build workflow, target architecture, checksum, signing identity, and software bill of materials. The download surface SHALL select or clearly label the matching platform and architecture and SHALL retain a source-install route as a fallback rather than representing source installation as the packaged path.

#### Scenario: Windows user downloads the stable installer
- **WHEN** a supported Windows/architecture client requests the stable tray download
- **THEN** the surface returns the matching signed installer plus version, checksum, and provenance

#### Scenario: macOS refuses an unnotarized stable artifact
- **WHEN** a stable macOS artifact lacks a valid project signature or notarization receipt
- **THEN** release publication fails and the artifact is not offered as stable

#### Scenario: Linux user chooses a supported format
- **WHEN** a Linux user visits the host download surface
- **THEN** the surface offers the signed Debian-family package and the portable Linux artifact with explicit compatibility notes

### Requirement: Installation is unattended-safe, reversible, and operating-system native
The installer SHALL place the application in the platform-standard application location, register only the minimum autostart/launcher integration needed by the tray, and make every privileged step visible to the operating system's native consent surface. Installation SHALL be idempotent for the same version, SHALL support repair/reinstall, and SHALL provide an uninstaller that removes program and autostart files without deleting user-owned universe content, exportable logs, or account state unless the user separately requests data deletion through its authoritative owner.

#### Scenario: Same-version installer runs twice
- **WHEN** the same signed installer is executed twice on one machine
- **THEN** the second run repairs or confirms the existing installation without creating duplicate autostart entries or tray processes

#### Scenario: User uninstalls the tray
- **WHEN** the user runs the native uninstaller
- **THEN** application binaries, updater, and autostart integration are removed
- **AND** user-owned content remains intact with a clear location or export path

### Requirement: First run binds the tray to the user's existing platform account
First run SHALL open the platform's supported browser authorization flow and bind the tray to the same account the user uses on chatbot/web surfaces. The tray SHALL validate the returned audience, issuer, expiry, state/nonce, and redirect binding before accepting credentials. A second machine SHALL create a distinct host identity under the same account rather than overwriting the first host. The implementation SHALL NOT require a second TinyAssets account or a per-launch copy/paste secret.

#### Scenario: Existing user completes browser authorization
- **WHEN** a signed-in user approves the tray authorization in their browser and the callback validates
- **THEN** the tray binds the local host to that account and records a distinct host identity

#### Scenario: Callback state does not match
- **WHEN** the authorization callback carries a missing or mismatched state/nonce or wrong audience
- **THEN** the tray refuses the credential, creates no host registration, and restarts authorization safely

#### Scenario: Same account installs on a second machine
- **WHEN** the same account authorizes a clean second installation
- **THEN** both machines remain separately addressable hosts under that account

### Requirement: Long-lived credentials use the operating system secret store
Refresh credentials and other reusable account secrets SHALL be stored through Windows Credential Manager/Credential Locker, macOS Keychain, or an available Linux Secret Service/libsecret provider. Stable releases SHALL NOT persist bearer or refresh secrets in plaintext preferences, command-line arguments, logs, crash reports, or environment files. If no supported secret store is available, the tray SHALL fail closed for persistent hosting and explain the remediation rather than downgrade to plaintext storage.

#### Scenario: Secret store is available
- **WHEN** authorization succeeds on a supported platform with a working native secret store
- **THEN** the reusable credential is stored through that service and ordinary preferences contain only a non-secret reference

#### Scenario: Linux secret service is unavailable
- **WHEN** no supported Linux secret store can persist the refresh credential
- **THEN** persistent hosting remains disabled with an actionable error
- **AND** no plaintext fallback credential is written

### Requirement: Productive self-host onboarding stays under five minutes
On a supported clean machine and ordinary broadband connection, the measured path from launching the downloaded installer to an online tray with at least one declared self-visible capability SHALL complete within five minutes at p95 for the acceptance cohort. The flow SHALL make capability selection optional, default every declared capability to `self`, keep `network` and `paid` opt-in, and defer payout configuration unless the user explicitly enables paid hosting.

#### Scenario: User accepts the default self-host path
- **WHEN** the user installs, authorizes, and accepts detected/default capability choices
- **THEN** the tray reaches online state with at least one self-visible capability within the measured friction budget
- **AND** no network or paid visibility is enabled implicitly

#### Scenario: User skips paid setup
- **WHEN** the user does not opt into paid hosting
- **THEN** onboarding completes without wallet, tax, or payout configuration

### Requirement: Offline and expired-auth states recover without false availability
If authorization or registration cannot complete because the network or origin is unavailable, the tray SHALL retain non-secret pending-onboarding state, display offline/pending status, and retry with bounded exponential backoff after connectivity returns. It SHALL NOT advertise the host or launch work that requires platform authority until credentials and registration are valid. Local-only work MAY continue when its separate local authority is valid. Expired credentials SHALL pause authority-requiring claims and attempt normal refresh without discarding local configuration.

#### Scenario: Network drops during first authorization
- **WHEN** first-run authorization cannot reach the origin
- **THEN** the tray remains installed in pending-registration state, shows an actionable offline message, and advertises no online host

#### Scenario: Registration succeeds after connectivity returns
- **WHEN** a pending installation regains connectivity and authorization completes
- **THEN** bounded retry registers the host once and onboarding resumes without reinstall

#### Scenario: Refresh fails for an online host
- **WHEN** the reusable credential expires and refresh is refused
- **THEN** authority-requiring daemons pause, the host stops advertising unavailable capacity, and the tray asks the user to sign in again

### Requirement: Autostart and singleton behavior survive packaging and upgrades
The installed application SHALL register one per-user autostart entry and SHALL enforce one tray control process per installation/user data root while allowing that process to manage multiple daemon children. Double launch, login autostart, repair, and updater restart SHALL converge on one tray process. Graceful shutdown SHALL stop or detach managed children according to explicit policy, publish offline presence best-effort, and release the singleton lease; a crash SHALL become offline after bounded presence expiry.

#### Scenario: Login and manual launch race
- **WHEN** autostart and a user double-click launch the same installation concurrently
- **THEN** one tray process owns the control lease and the other launch exits or focuses it without spawning duplicate children

#### Scenario: Tray closes cleanly
- **WHEN** the user chooses quit
- **THEN** managed processes follow the declared shutdown policy, the singleton lease releases, and host presence becomes offline directly or by bounded TTL

### Requirement: Updates are signed, atomic, channel-scoped, and recoverable
The tray SHALL support stable and opt-in pre-release update channels backed by signed manifests and signed platform artifacts. It SHALL verify signature, checksum, product identity, target platform/architecture, and monotonic allowed version before installation. Update application SHALL be atomic from the user's perspective: a crash or failed health check SHALL retain or restore the last known-good version. Critical security revocation MAY require an update or disable network hosting, but SHALL still surface the reason and preserve user content.

#### Scenario: Valid update passes health check
- **WHEN** a newer allowed-channel artifact validates and the restarted tray passes its readiness check
- **THEN** the new version becomes active and the previous version is retained only according to rollback/retention policy

#### Scenario: Update artifact is tampered
- **WHEN** artifact checksum or signature does not match the signed manifest
- **THEN** installation is refused, the current version keeps running, and a security event is recorded without exposing secrets

#### Scenario: New version crash-loops
- **WHEN** the updated tray fails the bounded post-update health check
- **THEN** the updater restores the last known-good version and reports rollback evidence

### Requirement: Tray observability excludes user content by default
The installed tray SHALL expose version, update channel, host/daemon/process readiness, active universe identifier, provider binding class, connectivity, capability visibility, queue summaries, and bounded error evidence needed to operate the host. Crash-report submission SHALL be opt-in and previewable; content, prompts, canon, attachments, secrets, raw filesystem paths, and private output SHALL be excluded by default. Presence and authoritative request/ledger transitions SHALL not be duplicated into a second analytics stream.

#### Scenario: User previews a crash report
- **WHEN** the tray offers an optional crash report
- **THEN** the preview contains bounded technical evidence and excludes declared content/secret/path fields before consent

#### Scenario: User declines crash reporting
- **WHEN** the user declines or never opts in
- **THEN** no crash payload is transmitted and ordinary host operation continues

### Requirement: Packaged release readiness is proven on clean supported systems and under fleet load
The packaged tray SHALL NOT be considered shipped until CI and independent acceptance install, authorize, start, upgrade, roll back, repair, and uninstall the exact release artifacts on clean supported Windows, macOS, Debian-family Linux, and portable-Linux environments. The proof SHALL measure the five-minute path, secret-store behavior, autostart/singleton races, origin outage recovery, simultaneous update checks, staged rollout, signature rejection, and no content loss. Build success without installing the produced artifact SHALL NOT satisfy this requirement.

#### Scenario: Clean-machine matrix exercises the release artifacts
- **WHEN** the release candidate is tested on the supported OS/architecture matrix
- **THEN** every cell installs the exact downloadable artifact and completes its declared onboarding and lifecycle checks

#### Scenario: Update service receives fleet-scale polling
- **WHEN** the declared §14 load concurrently checks for updates from the projected host fleet during a partial rollout and origin degradation
- **THEN** responses remain bounded, channel assignments remain stable, no unsigned artifact is accepted, and retries do not form an unbounded synchronized stampede
