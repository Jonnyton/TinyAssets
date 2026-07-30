## Why

The current OpenSpec drain stops when Jonathan's PC is off, so it cannot satisfy
the platform's zero-host uptime contract or prove that an ordinary user can
turn their own repository and spec into a continuously operated cloud
production loop. The approved design makes Jonathan's private main-universe
drain the first conformance instance of that generic, user-buildable pattern
without creating a privileged TinyAssets-only scheduler or consuming
maintainer compute.

## What Changes

- Define an ordinary, versioned, user-authored Branch composition for bounded
  OpenSpec delivery slices using existing Branch, Trigger, Goal, Gate, Run,
  effect, and cloud-executor primitives.
- Establish the shortest deployable BYOC-first slice: owner-bound provider
  authority, one persisted trigger, one cloud-authoritative activation epoch,
  one collision-safe active claim, one destination-scoped GitHub pull-request
  effect, normal review/CI, and a typed terminal receipt. Jonathan's
  TinyAssets/OpenSpec binding is the first production instance, not a
  hard-coded product special case.
- Expose inspection, pause/resume/stop, repair, immutable-version publication,
  activation, and rollback through an authenticated canonical chatbot
  connector so any owner can operate the loop from a phone while every
  personal device is off. Authenticated connector continuity is an
  implementation prerequisite, not only final acceptance evidence.
- Require a single-active cutover: the local tray drain stops before cloud
  acceptance and cannot drain concurrently with the cloud Branch.
- Gate final acceptance on cloud-worker restart recovery, at least 24 hours of
  useful PC-off progress, no duplicate claims, and rendered phone-chatbot proof.

## Capabilities

### New Capabilities

- `user-owned-cloud-automation`: Private-universe ownership, authority,
  continuation, external-effect, health, control, evolution, and acceptance
  requirements for a continuously running user-authored cloud Branch.

### Modified Capabilities

None. The new capability owns the automation-generic activation epoch and
single-active executor fence that do not exist in current-main specs. All other
missing implementation requirements remain owned by their current OpenSpec
changes.

## Impact

Implementation will eventually touch the cloud runtime and scheduler,
user-bound provider routing, Branch version/control actions, scoped GitHub
effect authority and receipts, and canonical connector status/control routing.
It depends on the active requester-BYOC, background authority, cloud scheduler,
and external-effect lanes rather than replacing them. No new top-level MCP
handle, maintainer credential path, market-compute prerequisite, desktop-only
control, or privileged product scheduler is introduced.
