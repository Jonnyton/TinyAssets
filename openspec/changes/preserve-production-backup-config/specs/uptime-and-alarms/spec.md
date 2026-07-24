## ADDED Requirements

### Requirement: Production deploy preserves and converges off-host backup authority

Application deployment and exact-source host-service installation SHALL
preserve a verified host-owned `BACKUP_DEST`, keep Spaces credentials confined
to root's rclone configuration, and provision the documented bucket-scoped
destination before enabling the backup timer only when both destination and
credential configuration are absent.

#### Scenario: Application deploy preserves canonical backup destination

- **WHEN** production already has a `BACKUP_DEST` assignment and an application deploy scrubs stale runtime overrides
- **THEN** the deploy leaves `BACKUP_DEST` unchanged
- **AND** it continues deleting the retired rename-era overrides

#### Scenario: Exact-source installer sees working backup configuration

- **WHEN** `BACKUP_DEST` and root's rclone configuration are both present and the configured destination probe succeeds
- **THEN** host-service installation reuses them without creating or rotating a Spaces key
- **AND** the backup timer remains enabled

#### Scenario: Exact-source installer sees completely absent backup configuration

- **WHEN** both `BACKUP_DEST` and root's rclone configuration are absent
- **THEN** the installer creates one bucket-scoped read/write key through the provider API
- **AND** targets the existing immutable external destination `spaces:workflow-backups-jonnyton-sfo3/workflow-backups`
- **AND** installs its credentials only at `/root/.config/rclone/rclone.conf` with root ownership and mode `0600`
- **AND** sets the nonsecret destination through the atomic TinyAssets environment installer
- **AND** retries the non-mutating destination probe within a bounded propagation window
- **AND** verifies the destination before enabling the backup timer

#### Scenario: Backup configuration is partial or invalid

- **WHEN** only one configuration half is present or the configured destination probe fails
- **THEN** installation exits red without overwriting or rotating the existing credentials

#### Scenario: New credential installation fails

- **WHEN** a newly created key cannot be installed and verified
- **THEN** failure cleanup removes any newly written destination/configuration and requests deletion of that exact new key
- **AND** no API token, Spaces secret, or provider response body reaches logs, outputs, artifacts, or the daemon environment
- **AND** provider failures expose only the HTTP or transport class plus an allowlisted error identifier/category derived without printing provider message text

#### Scenario: New credential has not propagated to the data plane

- **WHEN** the provider creates the scoped key but the destination probe initially returns access denied
- **THEN** the installer retries that same credential with bounded backoff
- **AND** does not create another key, broaden the grant, or enable the backup timer
- **AND** rolls back the key and host configuration if the propagation window expires

#### Scenario: Product rename does not rename external backup infrastructure

- **WHEN** product-facing source and documentation use the TinyAssets name
- **THEN** the installer and runbook retain the provider identity of the existing pre-rename Spaces bucket
- **AND** they do not silently substitute a similarly named bucket that has not been created and verified

#### Scenario: Operator explicitly exercises a production backup

- **WHEN** an exact-source manual host-service dispatch sets `run_backup` true
- **THEN** the workflow starts the installed backup service after convergence
- **AND** requires a successful service result and fresh brain/full archives at the primary destination
- **AND** scopes journal evidence to the new service invocation's exact systemd invocation ID
- **AND** requires two successful GitHub release asset uploads and the terminal backup completion marker from that invocation
- **AND** rejects any backup or retention warning/error from that invocation
- **AND** emits no environment-file contents, rclone configuration, or credential values

#### Scenario: Host-service installation does not request backup exercise

- **WHEN** a deploy-triggered run or manual dispatch leaves `run_backup` false
- **THEN** host services converge without starting the backup service

#### Scenario: GitHub release listing lags a successful upload

- **WHEN** a backup release and asset have been created successfully but the release-list endpoint has not yet returned that new release
- **THEN** retention boundedly waits for a list view that includes the newly created release before evaluating the prunable set
- **AND** each list request has an explicit transport timeout and the complete retry/sleep budget is at most two minutes
- **AND** an already-deleted victim returned by a stale list triggers bounded reconciliation rather than being counted as a successful deletion
- **AND** it deletes only the oldest recognized backup releases needed to leave at most `BACKUP_GH_RETAIN` recognized releases
- **AND** it never deletes an unrecognized parked or audit release
