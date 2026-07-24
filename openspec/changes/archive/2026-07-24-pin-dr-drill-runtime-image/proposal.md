## Why

Exact-landed DR run `30064143475` proved Debian 13 bootstrap, verified backup
transfer, exact restore, and representative-state SHA, then Compose rejected
the fresh host's intentionally empty `TINYASSETS_IMAGE`. A recovery drill
cannot prove the restored daemon until it supplies an immutable runtime image
without copying the primary host's secret-bearing environment.

## What Changes

- Read only the configured production daemon image reference from the primary
  host before provisioning.
- Normalize at most one documented matching pair of surrounding quotes, then
  require the exact canonical GHCR repository plus a SHA-256 digest and fail
  before resource creation when the value is missing or malformed.
- Pass the validated image only as an ephemeral Compose interpolation value
  while retaining the fresh host's template environment.
- Record the runtime image separately from the Debian Droplet image in terminal
  evidence.
- Rerun the production DR workflow only from the exact landed commit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: the fresh-host DR drill starts the daemon with the
  immutable image configured on the primary host without transferring the
  primary environment or secrets.

## Impact

- `.github/workflows/dr-drill.yml`
- `tests/test_dr_drill_workflow.py`
- `docs/ops/dr-drill-runbook.md`
- `openspec/specs/uptime-and-alarms/spec.md`
- production DR workflow evidence
