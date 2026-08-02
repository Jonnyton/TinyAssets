## Why

The current OpenSpec drain stops when Jonathan's PC is off, so it cannot satisfy
the platform's zero-host uptime contract or prove that an ordinary user-owned
cloud universe can sustain a useful workflow. The approved design moves that
loop into Jonathan's private main universe without creating a privileged
TinyAssets-only scheduler or consuming maintainer compute.

## What Changes

- Define an ordinary, versioned, user-authored Branch composition for bounded
  repository-to-accepted-spec delivery slices using existing Branch, Trigger,
  Goal, Gate, Run, evaluator, effect, and cloud-executor primitives. Jonathan's
  OpenSpec drain is the first acceptance fixture; runtime inputs are generic.
- Establish the shortest deployable BYOC-first slice: an immutable work
  definition, a read-only projection over existing authority owners,
  requester-owned provider authority, one persisted trigger, one
  cloud-authoritative activation epoch, one collision-safe active claim, one
  outbound-owned destination-scoped GitHub pull-request effect, normal
  review/CI, and a typed terminal receipt.
- Expose inspection, pause/resume/stop, repair, immutable-version publication,
  activation, and rollback through existing canonical chatbot handles so the
  loop remains operable from a phone while every user device is off.
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
safe distributed-execution, and outbound-boundary lanes rather than replacing
them. The first evaluator executes no tenant code and all shell/repository
commands fail closed until confinement ships. No new top-level MCP handle,
maintainer credential path, market-compute prerequisite, desktop-only control,
or privileged product scheduler is introduced.
