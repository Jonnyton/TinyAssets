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

**2. Keep a compute guard, but do not bill it.**
Effects-only accounting leaves a hole: a prompt-injected engine can still burn unlimited
CPU on runs that never emit an effect. So the admission gate stays — with a far higher
ceiling — as a safety bound. Preserve the existing asymmetry (`run_graph` fails open, remix
fails closed — Codex ADAPT 2026-08-22 #6): a DB blip must not wedge legitimate runs, but it
must not wave through an autonomous write either.

**3. Meter compute-minutes as wall-time, not CPU-time.**
A run holds one of four worker slots for its full duration, including time blocked on the
user's LLM. Wall-time is what actually consumes capacity, and it is what a user can reason
about. CPU-seconds would under-count the resource that is genuinely scarce.

**4. Storage is metered and capped, not charged — yet.**
`api/status.py:1252-1277` attributes only `checkpoint_db`, `activity_log` and
`universe_outputs` to a universe; the large pools (wiki, run transcripts) are shared/root.
Billing a number that excludes the biggest contributors would be dishonest. Attribute run
transcripts first, then revisit charging.

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
- **Unmeasured:** per-run CPU/RSS. Each run spawns a `codex exec`/`claude -p` subprocess, so
  memory may be the true users-per-box ceiling rather than the 4-worker pool. The capacity
  planning in the cost model is soft until measured on the droplet.
