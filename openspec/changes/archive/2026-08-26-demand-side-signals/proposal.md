## Why

`build-forward-platform-capabilities` records demand-side behavior as a cross-slice target, but it is an umbrella: its design decision D1 forbids implementing an independently deployable slice through it, so every slice must first become a narrower OpenSpec change. Its task 4.1 names the standing-goal / scheduling / onboarding / metrics half as **the cheapest slice to promote next**, precisely because it is *not* blocked on the unbuilt money transport. This change is that slice.

The scope is deliberately the non-monetary half. Umbrella task 4.2 (goal bounties, escrow, tranches, first-verified-claim settlement) and task 4.3 (the measured direct-service launch gate, which is additionally blocked on a host/founder parameter decision) both genuinely require the transaction transport and stay with the umbrella. Splitting them off is what makes 4.1 buildable today.

Nothing here is shipped behavior. What exists on `main` is adjacent, not equivalent: `shared-goals-and-convergence` owns the Goal primitive and its dispatch surface; `daemon-runtime-and-dispatch` owns a persisted cron/interval scheduler that explicitly **does not** backfill cron ticks missed during downtime; `outbound-boundary-layer` is the unbuilt owner of inbox ingress. No standing-goal record binds outcome, IANA-timezone schedule, budget posture, gates, and pause state as one durable object that keeps producing demand while its owner is away.

## What Changes

- Make a standing goal a durable record on the existing Goal catalog — outcome, owning principal, universe, explicit IANA-timezone cron-class schedule or event trigger, declared budget posture, success gates, pause state — that produces due work with no chatbot session open, and exposes a stable `(goal_id, schedule_period)` identity per due period for downstream idempotency.
- Derive standing-goal execution authority from the persisted owner bound server-side at registration; refuse caller-supplied, externally-written, and ambient-environment owner fields, and fail closed rather than falling back to a host or maintainer identity.
- Own the timezone-evaluated schedule that consumes `outbound-boundary-layer` inbox items: exactly one batch per eligible item, cutoff evaluated in the goal's own zone, receipts and period identity recorded, late items deferred rather than dropped or back-dated.
- Replace the scheduler's silent missed-cron-tick behavior with a per-schedule declared missed-tick policy (`skip` / `fire_once` / `backfill_bounded(n)`), recorded and reported, with bounded replays reusing the missed period's identity.
- Terminate onboarding in a running standing goal, built from **remixable commons archetypes** — a replaceable seed set, never a closed platform catalog — with the next scheduled action shown in the user's own timezone.
- Derive per-universe demand metrics on read, returned through the canonical read-only evidence handle, scoped to what the reader can already see, and never widening a counted goal's visibility.
- Keep this half non-monetary: no escrow, fee, price, ledger, or settlement record; a value-moving due action refuses and names the transaction transport owner instead of opening a second accounting path.
- Name the custody mode this lane assumes (platform-held coordination records) without encoding an answer to the open private-data custody question, and keep every persisted record exportable.

### Ownership boundaries

- **Consumes, does not redefine:** `shared-goals-and-convergence` (the Goal primitive, binding, gates, and the goal action surface), `identity-auth-and-access-control` (authenticated principal, visibility and ownership axes), `graph-execution-substrate` (compilation and run state), `constraint-evaluation` + `evaluation-outcomes-and-attribution` (gate evaluation and claim ordering).
- **Consumes an unbuilt owner:** inbox addressing, ingress, receipt, typing, and eligibility cutoff belong to `outbound-boundary-layer`. This change owns only the schedule that consumes eligible items and SHALL NOT define ingress or addressing. Until that owner lands, the inbox-consuming requirement is implementable only against its contract, not against a live inbox.
- **Delegates money:** every value-moving consequence settles through the single authenticated double-entry transaction boundary owned by the `paid-market-economy` capability (whose transport `paid-market-track-e-wave-2-transport` is currently building). Normative text here names the *capability*, not the change slug — change names expire on archive, capabilities do not. This change creates no accounting path and no payment surface.
- **Delegates published demand aggregates:** the bucketed, k-anonymized, off-by-default `TINYASSETS_DEMAND_SIGNAL` contract is owned by `paid-market-live-price-discovery`. This change defines no second aggregation or publication path.
- **Leaves with the umbrella:** goal-bounty posting/escrow/claims/refunds (task 4.2) and the measured direct-service volume gate and its parameters (task 4.3).
- **Supersession is carried as deltas, not as promises:** two as-built requirements contradict this target — the scheduler's silent missed-tick behavior in `openspec/specs/daemon-runtime-and-dispatch/spec.md`, and the **fixed** `goals` action table in `openspec/specs/shared-goals-and-convergence/spec.md`. Both contradictions are carried here as MODIFIED deltas. `demand-side` SHALL NOT sync without them — a synced standing-goal guarantee beside an unmodified "cron ticks are silently dropped" limitation, or beside an action table that no longer matches, is the exact drift `reclassify-forward-vision-specs` removed.

## Capabilities

### New Capabilities

- `demand-side`: durable standing goals, persisted-record execution authority, timezone-evaluated inbox batching, commons-archetype onboarding that ends in a running goal, owner-scoped derived demand metrics, a named custody assumption, and a fail-closed money edge.

### Modified Capabilities

- `daemon-runtime-and-dispatch`: the persisted scheduler requirement gains a required IANA timezone per cron-class schedule, a declared and recorded missed-tick policy with a determinate period identity under every policy, and explicit DST gap/overlap semantics — replacing the as-built behavior in which cron ticks missed during downtime were silently dropped. Only that requirement is modified; `operator-request-trigger-contract` owns the *dispatcher* requirement in the same capability and is untouched, so the two changes do not collide.
- `shared-goals-and-convergence`: the Goal record carries the standing-goal coordination fields, and the fixed `goals` action table gains `set_schedule`, `clear_schedule`, `pause`, and `resume`. The as-built requirement specifies that table as **fixed** and enumerates it, so extending it changes that requirement; asserting the extension only in the `demand-side` delta would leave canonical truth describing a table that no longer matches. Nothing else in the capability is touched.

All three deltas are unsynced targets. Canonical truth stays as-built until this change is implemented and synced, and `demand-side` SHALL NOT sync without both MODIFIED deltas.

### Released from the umbrella

`build-forward-platform-capabilities` task 4.1 names this change as its owner. Two requirements were **physically moved** out of the umbrella's `demand-side` delta into this change — *Standing goals are durable demand independent of chat sessions* and *Onboarding terminates in a useful running goal* — so that each requirement keeps exactly one active owner, matching the release pattern used for umbrella tasks 1.1, 1.2, and 2.1. This is a **partial** release: the umbrella retains the three bounty and direct-service requirements pending tasks 4.2 and 4.3, so the `demand-side` capability has two active owners split by requirement, not two owners of the same requirement.

## Impact

This is an active, unimplemented target change. Nothing in it is shipped behavior, nothing here may be synced into `openspec/specs/` while it is unbuilt, and `openspec archive` MUST NOT be run against it (archive syncs deltas as a side effect). On implementation it will affect the Goal record and its storage migration, the scheduler's schedule table and tick loop, the proactivity heartbeat's authority resolution, onboarding and archetype surfaces, the read-only status/evidence surface, and commons archetype content. It depends on the umbrella's cross-slice invariants D1–D8, on `outbound-boundary-layer` for inbox ingress, on `daemon-runtime-and-dispatch` for the heartbeat and scheduler, and on `shared-goals-and-convergence` for the Goal primitive. Any public surface it exposes additionally requires the §14 concurrency/load proof, live connector canaries, a rendered chatbot conversation, and freshness-stamped post-fix clean-use evidence before it is treated as landed.
