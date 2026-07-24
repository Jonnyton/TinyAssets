## Why

The production deploy workflow deletes `BACKUP_DEST` from the host environment,
so every application deploy disables the required nightly off-host backup until
an operator manually repairs it. The exact-SHA host-service exercise exposed
this regression in production: all other uptime jobs completed, while backup
failed before creating either tier.

## What Changes

- Preserve the canonical `BACKUP_DEST` assignment across application deploys.
- Continue deleting genuinely retired `WORKFLOW_*` and workflow-named
  overrides.
- Add executable workflow-contract coverage that prevents backup configuration
  from being classified as stale runtime state again.
- Correct the runbook's historical "current droplet" claim and record fresh
  production backup evidence after configuration is restored.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: Require application deploys to preserve host-owned
  off-host backup configuration and require the installed backup service to
  remain executable after a deploy.

## Impact

Affected surfaces are `.github/workflows/deploy-prod.yml`, its structural
tests, the production host's root-owned rclone configuration, the backup
runbook, and the host-uptime verification audit. No daemon API or stored data
shape changes.
