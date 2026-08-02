## Why

The local OpenSpec drain stayed process-active for 24 attempts while completing zero implementation slices because refinery workers converted every eventual acceptance gate into a current `Depends` blocker. Visible backlog must not collapse into endless coordination PRs or truthful-but-useless idle: the refinery must expose the next executable slice or the concrete prerequisite slice that makes it executable.

## What Changes

- Define `STATUS.md` `Depends` as immediate admission prerequisites for the exact row, not a list of downstream completion, proof, deployment, or organic-use gates.
- Require a refinery worker to search unchecked tasks for one bounded slice that is executable now; later gates remain in the row's acceptance text or OpenSpec tasks.
- When no direct slice is executable, require the refinery to promote the shortest concrete autonomous prerequisite-removal slice rather than another umbrella blocker row.
- Treat a refinery result as a continuation only when current main exposes a claimable implementation or prerequisite-removal row; retain honest `BLOCKED` only when no autonomous prerequisite slice exists.
- Publish delivery-stall evidence when coordination attempts continue without a completed implementation slice so tray health cannot imply productive draining.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: refinery admission, dependency semantics, continuation validation, and delivery-progress health become implementation-oriented.

## Impact

The change affects the OpenSpec drain supervisor and focused tests, the cross-provider OpenSpec drain convention in `AGENTS.md`, the canonical development-coordination requirement, and local tray/watchdog observability. It does not change product APIs, public MCP behavior, provider credentials, or the cloud-drain runtime.
