## Why

Fresh production hosts do not install the disk-pressure timer or the second
watchdog path, and rerunning bootstrap leaves current-but-disabled backup,
watchdog, and prune timers disabled. That makes the canonical uptime layers
depend on host history instead of converging from source on every install.
The fresh-host env template also advertises unused `STORAGEBOX_*` fields while
the canonical backup implementation requires `BACKUP_DEST`, so following the
runbook cannot configure the timer successfully.

## What Changes

- Add one fail-closed host uptime installer for the canonical watchdog,
  backup, prune, and disk-pressure unit/runtime asset set.
- Make both fresh-host bootstrap and the post-deploy host-service workflow use
  that installer, and make the restart workflow's install option delegate to
  it instead of installing one watchdog independently.
- Synchronize unit-executed scripts with their units and always enable, start,
  and verify every required timer, even when installed files were already
  current.
- Pin automatic reconciliation to the triggering deploy SHA, checksum a private
  bundle, quiesce timers without killing active oneshots, and activate one
  content-addressed runtime atomically.
- Wait boundedly for every same-target caller to converge while allowing
  independent host roots to install concurrently.
- Make the fresh-host env template and runbook expose the canonical
  `BACKUP_DEST` plus root-owned rclone configuration path.

## Capabilities

### New Capabilities

<!-- None. -->

### Modified Capabilities

- `uptime-and-alarms`: require fresh-host and repeat-install convergence for
  every shipped host uptime timer and its directly executed runtime assets.

## Impact

- `deploy/hetzner-bootstrap.sh` and a new shared host uptime installer.
- `.github/workflows/install-host-services.yml` upload/install behavior.
- Production systemd unit and host script ownership, enablement, activation,
  and verification.
- `deploy/tinyassets-env.template` backup configuration truth.
- Focused isolated-host and concurrent installer tests plus operator guidance.
