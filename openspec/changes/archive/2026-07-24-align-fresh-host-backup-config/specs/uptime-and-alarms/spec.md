## ADDED Requirements

### Requirement: Fresh-host backup configuration matches the runtime contract

The fresh-host environment template SHALL expose the canonical `BACKUP_DEST`
consumed by the root-run backup service and SHALL NOT present unused
`STORAGEBOX_*` fields as sufficient backup configuration. Active operator
guidance SHALL direct operators to configure the named rclone remote as root,
store its configuration at `/root/.config/rclone/rclone.conf` with root
ownership and mode `0600`, and keep destination credentials out of the shared
daemon environment file.

#### Scenario: Operator follows fresh-host backup setup

- **WHEN** an operator configures backup shipping from the fresh-host template and active runbook
- **THEN** the service receives `BACKUP_DEST`
- **AND** root's rclone lookup resolves the documented credential file
- **AND** no unused `STORAGEBOX_*` value is presented as runtime configuration
