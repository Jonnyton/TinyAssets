# Align fresh-host backup configuration

## Why

The root-run backup service consumes `BACKUP_DEST` and root's rclone
configuration, but the fresh-host template still presents unused
`STORAGEBOX_*` values and operator guidance points at a configuration path the
service does not read. A correctly installed timer therefore remains unable to
ship backups after following the documented setup.

## What Changes

- Replace unused `STORAGEBOX_*` template fields with `BACKUP_DEST`.
- Direct operators to configure and protect root's canonical rclone file.
- Correct the active backup/restore runbook and backup unit comments that
  falsely describe `/app` or `STORAGEBOX_*` credential lookup.
- Add a static contract test spanning the template and active runbooks.

## Capabilities

### Modified Capabilities

- `uptime-and-alarms`: Fresh-host backup configuration matches the root-run
  backup service's actual destination and credential lookup.

## Impact

This is a prerequisite increment for PR #1658. It changes configuration
guidance only; backup execution and timer installation remain owned by the
convergent host-installer change. PR #1658 must rebase after this lands and
remove its overlapping configuration/spec delta before merge.
