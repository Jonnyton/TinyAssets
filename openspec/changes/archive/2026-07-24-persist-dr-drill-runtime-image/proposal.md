## Why

Exact-landed DR run `30065054549` proved Debian 13 bootstrap, verified backup
transfer, exact restore, and Compose image startup, but the restored daemon
restart-looped because the validated runtime digest was used only for Compose
interpolation and the fresh template still exposed no populated startup
sentinel to the container. The retained host became healthy and passed MCP
initialization after only that public digest was written to the template.

## What Changes

- Write the already validated canonical runtime image reference into the fresh
  drill host's `TINYASSETS_IMAGE` template assignment before Compose startup.
- Preserve the rule that no production environment file or secret is copied.
- Make the workflow fail if it cannot update exactly one template assignment.
- Add an explicit cleanup-only dispatch path so a retained drill Droplet can be
  identity-checked and destroyed with the repository's existing DigitalOcean
  credential without provisioning another host.
- Rerun the production DR workflow only from the exact landed commit and
  require daemon health, MCP initialization, and successful Droplet deletion.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `uptime-and-alarms`: the fresh-host DR drill persists only the validated
  nonsecret image digest into its local template, and operators can invoke a
  bounded cleanup-only path for a known retained drill Droplet.

## Impact

- `.github/workflows/dr-drill.yml`
- `docs/ops/dr-drill-runbook.md`
- `openspec/specs/uptime-and-alarms/spec.md`
- production DR workflow and cleanup evidence
