## Why

Epoch-2 branch work can remain queued indefinitely because production intentionally runs no provider-shaped worker fleet. The daemon must consume that work on each universe's own assigned serving credential without widening the interactive serving grant or permitting ambient fallback.

## What Changes

- Add a distinct `background_branch_run` provider-work operation with immutable-branch role and spend ceilings.
- Extract claimed branch execution into a shared runtime callable used by both `fantasy_daemon` and the daemon consumer.
- Add a bounded, stoppable daemon-owned assigned queue consumer behind `TINYASSETS_ASSIGNED_QUEUE_CONSUMER`, default off.
- Add lease/epoch/version CAS claiming, retryable authority holds, per-universe spend limits, and a global concurrency cap.
- Preserve the existing fleet, deployment, scheduler path, and all production flags unchanged.

## Capabilities

### New Capabilities

- `assigned-queue-execution`: Dark daemon-owned execution of epoch-2 immutable branch tasks on the task universe's current assigned serving credential.

### Modified Capabilities

- `provider-routing`: Add a non-interactive, exact-universe background operation that never borrows interactive `converse` permission or ambient credentials.
- `daemon-runtime-and-dispatch`: Start and stop the bounded consumer only when its opt-in environment flag is enabled.
- `background-branch-execution-authority`: Bind assigned-consumer task claims and provider launches to the current activation epoch, immutable target, background attempt, and lease fence.

## Impact

Touches provider assignment/routing, provider-work authority, epoch-2 queue claims, claimed-task execution, daemon startup, focused tests, and the generated Claude-plugin runtime mirror. It does not change compose/deploy, prune fleet code, enable the flag, or mutate production.
