## Context

Production serves the HTTP daemon without the old provider-shaped worker services, while epoch-2 automation tasks still require a provisioned worker/runtime/provider tuple. `.fleet_plan.txt` approves a strangler slice: retain all old paths, add one daemon-owned consumer, and keep it inert until an explicit environment flag is enabled.

The existing interactive serving binding is deliberately only `converse`/`writer`. Background execution already has separate immutable target bindings and attempts. Provider assignment owns the current provider and credential custody. These domains must be composed without letting any one of them promote the others.

## Goals / Non-Goals

**Goals:**

- Execute claimed epoch-2 immutable branch tasks through the task universe's current assigned provider.
- Re-read queue/admission, activation, background binding/attempt, assignment, custody, immutable branch roles, and budgets before every provider launch.
- Prevent duplicate claims and retry budget reminting with durable task/attempt identity and lease CAS.
- Keep daemon uptime independent from task failures and bound total concurrency.

**Non-Goals:**

- Enabling the consumer, changing deploy/compose, pruning fleet code, reconciling stale production rows, or changing scheduler routing.
- Treating an interactive serving grant, queue lease, task payload, environment provider, or legacy worker record as background provider authority.
- Deep post-live load hardening beyond the focused adversarial tests required for this dark slice.

## Decisions

1. **Separate background provider-work binding.** `background_branch_run` receives its own provider-work binding identity, role set, invocation/token/cost ceilings, receipts, claims, and reservations. The current serving assignment supplies only provider selection and custody; its `converse` binding remains unchanged. A combined serving/background binding was rejected because it would silently widen founder-turn authority.

2. **One launch fence under assignment admission.** Each actual provider call holds the universe assignment's shared admission fence while one SQLite transaction revalidates the task/admission digest and generation, activation epoch and immutable subject, background binding and attempt, owner, assigned provider, background provider binding, custody tuple, lease, and remaining budgets. The provider snapshot and durable invocation reservation are created before launch and the snapshot is removed in `finally`. Rotation uses the exclusive admission fence, so it either precedes launch and is observed or follows the fenced call.

3. **Approved roles come from the immutable version.** The consumer derives the closed role set from the pinned branch snapshot's prompt nodes, defaulting empty model hints to `writer`, and rejects unknown roles. Policies cannot select a provider other than the current assignment.

4. **Process lease, not fake provider worker.** The consumer has a boot-unique `consumer_id` and lease. Queue claiming validates the exact activation epoch, subject/version/digest, background attempt, and serving readiness inside the existing `BEGIN IMMEDIATE` claim transaction. Persisted `claimed_by` remains an opaque executor identifier for compatibility.

5. **Shared executor with an explicit identity object.** The neutral runtime function receives the storage root, claimed task, `ClaimedBranchExecutorIdentity`, and provider call. `fantasy_daemon` remains a wrapper and the daemon consumer supplies its own identity and heartbeat callback. Run reservation, immutable version execution, cancellation, receipts, continuation fences, and delegated authorization inputs remain unchanged.

**Reconciled execution shape (2026-08-24).** `AssignedQueueConsumer` claims only with its boot-unique process `AssignedConsumerLease`; after claiming, it reuses the active background Branch binding's owner-authorized `daemon_id` and `runtime_id` to hydrate `ClaimedBranchExecutorIdentity`, terminalizing with a named reason when that binding or identity is unavailable. Inside the launch fence, each provider call issues/reuses the `background_branch_run` provider-work binding, durable receipt and execution claim, then arms exactly one `ProviderInvocationCarrier` for the router's `UniverseContext`; it never fabricates a descriptor worker or build identity, routes through the cloud-worker audience path, or supplies caller-populated `served_provider` authority.

6. **Bounded failure containment.** The consumer owns one coordinator thread and a fixed-size executor. It permits one active task per universe and a small global maximum. An authority failure releases the exact claim to a retryable authority-held projection; arbitrary task exceptions are logged and terminalized without escaping the worker future or daemon main thread.

## Risks / Trade-offs

- **[Cross-store TOCTOU]** → Assignment admission fences provider rotation while the launch transaction re-reads all shared SQLite roots immediately before arming.
- **[Retry after ambiguous launch]** → Reuse the same background attempt/receipt and refuse conflicting or already-launched reservation evidence; do not mint a new attempt budget.
- **[Long provider calls delay rotation]** → Rotation waits behind the shared admission fence; correctness is preferred to mid-call credential substitution.
- **[Legacy rows carry worker audiences]** → The assigned consumer treats those fields as compatibility provenance only and requires current activation/background/consumer lease facts instead.
- **[HTTP process pressure]** → Global and per-universe caps are hard defaults; task failures stay inside futures.

## Migration Plan

Land dark with `TINYASSETS_ASSIGNED_QUEUE_CONSUMER` absent/off. Existing fleet and scheduler behavior remains. A later host-authorized slice may reconcile stale rows and enable one universe; rollback is clearing the flag. No production action belongs to this change.

## Open Questions

None for the dark build. Load-derived tuning of concurrency and spend ceilings remains post-live hardening.
