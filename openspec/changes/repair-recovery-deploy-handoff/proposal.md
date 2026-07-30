## Why

Production run `30578541098` proved that a successful emergency recovery can
leave the exact five stopped containers owned by a recovery-specific Docker
Compose project. The next normal deploy then fails before service start because
the canonical systemd Compose project cannot create the same fixed container
names.

## What Changes

- Add a fail-closed handoff from a finalized recovery generation to the next
  normal fenced deploy.
- Permit removal only of the exact five stopped, restart-fenced containers
  whose identities and recovery Compose project are recorded in durable fence
  state.
- Refuse partial, running, changed-identity, foreign-project, extra-writer, or
  otherwise unproved fleets without mutating Docker.
- Preserve the production data volume and every non-recorded container.
- Record the retired recovery generation before the canonical service may
  start, so retries remain bounded and auditable.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: extend the existing emergency-fenced recovery
  contract with a safe, provenance-bound transition back to the canonical
  deployment project.

## Impact

The change affects the transitional production deploy-fence controller and its
focused tests. It unblocks normal immutable deployments, including PR #1935's
OAuth diagnostics, without changing public MCP behavior, authentication, data
formats, or the long-term retirement plan that deletes this controller.
