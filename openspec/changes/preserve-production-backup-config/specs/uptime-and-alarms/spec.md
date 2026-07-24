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
- **AND** verifies the destination before enabling the backup timer

#### Scenario: Backup configuration is partial or invalid

- **WHEN** only one configuration half is present or the configured destination probe fails
- **THEN** installation exits red without overwriting or rotating the existing credentials

#### Scenario: New credential installation fails

- **WHEN** a newly created key cannot be installed and verified
- **THEN** failure cleanup removes any newly written destination/configuration and requests deletion of that exact new key
- **AND** no API token, Spaces secret, or provider response body reaches logs, outputs, artifacts, or the daemon environment
- **AND** provider failures expose only the HTTP or transport class plus an allowlisted error identifier/category derived without printing provider message text

#### Scenario: Product rename does not rename external backup infrastructure

- **WHEN** product-facing source and documentation use the TinyAssets name
- **THEN** the installer and runbook retain the provider identity of the existing pre-rename Spaces bucket
- **AND** they do not silently substitute a similarly named bucket that has not been created and verified
