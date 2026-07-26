## Why

TinyAssets can execute a branch after the authorizing chatbot request has ended
through schedules, subscriptions, daemon soul loops, claimed branch tasks, and
graph-enqueued child work. Those paths currently reconstruct authority from
caller-supplied owner strings, public visibility, queue possession, or process
environment instead of a durable server-issued grant, so they cannot safely
support private branches or prove who authorized unattended work.

## What Changes

- Introduce a durable, server-owned background branch binding plus a
  single-attempt claim. The binding records who authorized which operation
  against which universe and branch; the attempt pins the exact current target
  and executor after revalidation.
- **BREAKING**: stop treating `owner_actor`, `UNIVERSE_SERVER_USER`, trigger
  ownership, queue claims, daemon identity, or branch visibility as execution
  authority. Legacy rows that cannot be proven from canonical identity and ACL
  records become inactive and require authenticated reauthorization.
- Make schedule/subscription creation, daemon loop declaration, claimed-task
  dispatch, and graph child enqueue persist only opaque binding references and
  fail closed when the binding is absent, stale, revoked, exhausted, or no
  longer authorized.
- Bind daemon loop authority to a pinned `soul.md` version and rotate or revoke
  it when governed learning changes the declared loop.
- Preserve the existing graph lineage, depth, run-budget, universe, and
  concurrency guards while adding explicit attenuation for child target
  authority.
- Keep target authority separate from scheduling reservations, daemon control,
  distributed B2 execution grants, provider-work receipts, provider-attempt
  receipts, and payment/effect authority; none may be promoted into another.
- Define an inventory, dark-mode, migration, and rollback path that never
  guesses authority for legacy schedules, subscriptions, soul loops, or queued
  work.
- Add concurrency and failure-injection proof for duplicate firing, revocation
  races, mutable branch/soul updates, crash boundaries, and multi-host claims.
- Keep the connector actions as the canonical user path. No Agent Village or
  web-app surface is required by this change.

## Capabilities

### New Capabilities

- `background-branch-execution-authority`: Durable target bindings,
  single-attempt claims, revalidation, attenuation, revocation, migration, and
  audit rules for branch work that outlives its authorizing request.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: Schedules, subscriptions, daemon soul loops,
  and claimed branch tasks require valid background target authority before
  dispatch.
- `graph-execution-substrate`: In-node child enqueue carries attenuated target
  authority without weakening physical-universe, lineage, depth, budget, or
  concurrency guards.
- `universe-lifecycle-and-soul`: A declared loop branch and its background
  authority are versioned and changed as one recoverable lifecycle.
- `distributed-execution`: Queue reservations, B2 execution grants, target
  authority, and provider authority remain distinct and are all required where
  their domains apply.

## Impact

The change affects authenticated scheduler handlers and storage,
`tinyassets/scheduler.py`, universe soul creation/editing, branch-task storage
and graph enqueue, daemon and cloud-worker dispatch, distributed worker
admission, provenance/audit records, migration tooling, and their concurrency,
crash-recovery, connector, and rendered-chatbot tests. It consumes the existing
identity/ACL, daemon-identity, branch-access, provider-execution, and
provider-attempt contracts rather than redefining them.
