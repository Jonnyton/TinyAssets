## Why

The current full-volume restore clears the live Docker volume before it has
proved that the selected archive is valid and extractable. A damaged or
truncated release backup can therefore turn a recoverable incident into data
loss during a recovery drill.

## What Changes

- Validate and extract a selected full-volume archive into a unique staging
  directory beside the target volume before changing the live data.
- Replace destructive in-place extraction with a same-parent directory swap
  that rolls the previous volume back if the replacement move fails.
- Support an explicitly selected, locally downloaded archive through the
  existing environment-driven restore interface, for GitHub Release recovery.
- Document the restore safety contract and cover successful, corrupt, rollback,
  and concurrent restores with executable tests.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `uptime-and-alarms`: strengthen the full-volume restore behavior used by the
  backup and manual fresh-host recovery drill.

## Impact

- `deploy/backup-restore.sh` restore sequencing and archive source selection.
- Backup restore tests and the operator runbooks for GitHub Release recovery.
- No service is started by the restore script; the existing caller-owned start
  step remains unchanged.
