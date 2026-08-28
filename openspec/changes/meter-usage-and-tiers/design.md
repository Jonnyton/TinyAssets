## Context

`_engine_run_admit()` (`tinyassets/engine_mcp_server.py:86-148`) is a single rolling-window
admission gate: it counts rows in `.engine_run_admissions.db` keyed on `universe_id`, inside
one `BEGIN IMMEDIATE` transaction so parallel callers cannot both slip past the cap. That
atomicity is correct and should be preserved — it closes a real TOCTOU race.

What is wrong is *where* it counts and *how many things* it counts for. Four call sites share
the one ledger — `run_graph` (`:377`), `write_graph` (`:884`), and two engine write paths
(`:1163`, `:1405`) — so authoring a branch and running it draw down the same 20/hour. On
2026-08-28 that is precisely what happened: the universe spent its budget building a repair
and had none left to run it.

The measured economics (2026-08-28) frame the sizing, and the first pass got one of them
badly wrong. Inference is BYO and therefore free to us, and WorkOS is free to 1M MAU, so
per-user *compute* really is cheap. But **storage per universe is ~515 MB, not the ~20 KB
`get_status` reports** — measured on the droplet, and dominated by a per-universe copy of
the provider runtime (`.runtime/provider-child` 315 MB, `.credentials/codex` 119 MB,
`.runtime/provider-launch-credentials` 81 MB) against ~0.9 MB of actual user content. See
`docs/concerns/2026-08-28-per-universe-storage-is-515mb-of-duplication.md`.

The live box is 1 vCPU / 2 GB / 50 GB ($12/mo, not the $24 first assumed), 69% full, with
13.4 GB of that reclaimable. At 515 MB/universe, ~100 users would fill it on storage alone.

Two consequences for this design: storage is a **real** dimension after all and worth
capping; and the biggest available cost lever is not pricing but deduplicating that
provider runtime — which would return per-universe storage to ~1 MB and is tracked
separately from this change.

## Goals / Non-Goals

**Goals:**
- Effects, and only effects, draw down the billable budget.
- Compute is bounded by a separate, generous guard that exists for safety, not revenue.
- Limits are per-universe and configurable; a tier record decides them.
- Usage is reported to Stripe without Stripe leaking into the rest of the codebase.
- A refusal says which budget ran out and when it refills.

**Non-Goals:**
- GPU metering — we own no GPUs and buy no inference. The third dimension is CPU
  run-minutes on our own box.
- Charging for storage now. Storage is metered and capped; it is not billed until
  attribution is honest (see Decisions).
- Replacing `paid-market-economy`. That capability is the bid/goal marketplace; this is
  subscription metering and they are separate concerns.
- Multi-seat, org accounts, or annual plans.

## Decisions

**1. Reserve the effect budget pre-flight; settle it on outcome.**

The naive fix — count at `finalize_receipt(... STATUS_SUCCEEDED)` — is wrong, and it is
worth writing down why, because it looks right. Counting only on success makes the cap
**post-hoc**: the effect has already reached the world before the meter moves. For an
irreversible outbound action that is not a control at all, and it would reopen the security
gate this bound exists to provide (Codex gate #5).

Instead, reuse the reservation lifecycle `external_write_receipts.py` already has:

| Point | Existing primitive | Quota action |
|---|---|---|
| Before the write | `try_reserve_receipt` (atomic) | **reserve** a slot; refuse here if the budget is exhausted |
| Write failed | `release_reservation` | **release** the slot — a failure costs nothing |
| Write succeeded | `finalize_receipt(SUCCEEDED)` | **commit** the slot |

This gets both properties at once: enforcement happens *before* the effect (a real control,
bounded even under concurrency, since reservation is atomic), and failed attempts still cost
the user nothing — which was the whole point of tonight's outage. Held and released receipts
release; replay finds the existing reservation rather than taking a second one.

*Rationale:* counting attempts punishes debugging; counting only successes stops being a
security control. Reserving is the only shape that satisfies both, and the repo already has
the primitive.

**1a. Settlement is one transition-sensitive operation, not three hooks.** Cross-family
review (Codex, 2026-08-28) showed the receipt lifecycle is *state*-idempotent but not
*accounting*-idempotent, so hooking the three obvious functions both double-counts and
leaks:

- `finalize_receipt` does not require the prior status to be `pending`
  (`external_write_receipts.py:685`) and returns `True` when replayed against an
  already-succeeded row (`:697`) — incrementing on a truthy return **double-counts**.
- Reconciled success reaches `succeeded` via `finalize_reconciliation()`, never
  `finalize_receipt` (`effectors/outbound_boundary.py:559`) — a **bypass**.
- A confirmed hold goes `held`/`failed` → `pending` (`:894`) and is then invoked
  (`outbound_boundary.py:203`) **without calling `try_reserve_receipt`** — so a held effect
  can fire with no quota admission at all.

Therefore: settlement SHALL be a single operation keyed by receipt identity that fires only
on an actual transition *into* terminal success, covering normal success, reconciled
success, and confirmed-hold activation; and confirmed-hold activation SHALL reserve quota
before invoking. The ledger write must be atomic with the receipt transition (or go through
a uniquely-keyed outbox) — "update receipt, then increment ledger" cannot be exactly-once.

**2. Keep a compute guard, and make it fail closed.**
Effects-only accounting leaves a hole: a prompt-injected engine can still burn unlimited
CPU on runs that never emit an effect. So the admission gate stays, with a far higher
ceiling, as a safety bound.

It must **fail closed**, reversing the current posture. The old fail-open was justified when
this same gate also bounded effects and the approved-source gate was the primary control;
once effects are separately reserved, compute is this gate's *only* job, and a gate that
admits everything when its ledger errors does not do that job. Codex (2026-08-28) showed the
teeth: `ThreadPoolExecutor.submit()` queues without bound (`runs.py:3002`, `:3257`), so the
4-worker pool limits *simultaneous* execution but not *accepted* work — during a ledger
outage an injected engine can create unlimited queued runs, durable rows and transcripts.
The allowlist and readable-branch checks constrain *what* runs, never *how often*
(`engine_mcp_server.py:352`, `:392`).

Scope the reversal to the **engine-triggered** path. Ordinary browser/user run submission
stays outside this dedicated gate and is unaffected.

**3. Meter compute-minutes as *worker-held* wall-time, bounded.**
A run holds a worker slot for its full duration, including time blocked on the user's
provider, so wall-time is what consumes capacity. But it must be measured from **worker
acquisition**, not from enqueue: `runs.started_at` is written while the run is still
`queued` (`runs.py:797`), the pool submit happens later (`:3257`), and moving to `running`
does not reset it (`:2417`) — so `finished_at - started_at` includes arbitrary queue delay,
and platform load would inflate a user's bill. Codex, 2026-08-28.

Three further requirements fall out:
- A **maximum chargeable duration** per run. Provider calls have individual timeouts (e.g.
  600 s absolute for Claude, `providers/base.py:83`) but nothing bounds a whole multi-node run.
- **Crash handling.** Restart marks queued/running rows interrupted with the restart time
  (`runs.py:3844`); a terminal-only meter under-counts a crash, while a live
  `now - started_at` meter accrues forever. Settle interrupted runs at the capped duration.
- **Idempotent settlement keyed by `run_id`**, so a retried settlement cannot double-charge.

**4. Storage is metered and capped, not charged — yet.**
`api/status.py:1252-1277` attributes only `checkpoint_db`, `activity_log` and
`universe_outputs`, which is why it reports 20 KB for a universe that is really 516 MB.
Billing a number that misses 99.8% of the footprint would be dishonest, and charging for
storage that is ~99% *our own duplicated provider runtime* would be worse — the user did not
put it there. Fix attribution first; dedupe the runtime; then revisit charging.

**5. One ledger, three dimensions.**
Effects, compute-minutes and storage report from a single per-universe usage ledger. The
alternative — three subsystems each with their own store — multiplies the failure modes and
makes a coherent "what did this universe use" answer impossible.

**6. Stripe sits behind an adapter and never leaks.**
Metering writes to our ledger unconditionally. The billing adapter reads that ledger and
reports Billing Meter events keyed by the WorkOS `sub`
(`docs/reference/workos-authkit-integration.md:58` — already canonical, and stable where
email is not). *Rationale:* the meter must stay correct when Stripe is down, enforcement
must never depend on a third party being reachable, and the processor must stay swappable.

**7. Free tier is the absence of a subscription.**
Not a separate plan record. One paid tier at $20/month. Fewer states, less to drift.

## Risks / Trade-offs

- **A generous free tier is abusable in a way a tight one is not.** Mitigated by the
  compute guard and by effects being the thing actually capped — the expensive-to-others
  action is the one metered.
- **Wall-time metering charges users for our slowness.** If a run is slow because the box
  is loaded, the user's meter still ticks. Accept for now; revisit if it bites.
- **The BYO-LLM rule is load-bearing economically, not just architecturally.** Every number
  in the cost model dies if the platform ever supplies inference. Worth stating in
  `PLAN.md` so it is not casually reversed.
- **Effect counting changes a security-relevant gate.** The current bound is a Codex
  security finding; loosening the wrong half would reopen it. Requires cross-family review
  before landing (`AGENTS.md` § Quality Gates — authority/public-surface change).
- **Measured 2026-08-28:** the box is 1 vCPU / 1,967 MB, daemon RSS 449.6 MiB, ~1.1 GB free.
  Four concurrent provider subprocesses will not fit, so `runs.py:3002`'s 4-worker pool is
  over-provisioned for this hardware and **memory is the concurrency ceiling**. Per-run RSS
  under load is still unmeasured — take it during the live verification in 4.3.
