> **Target-only change — nothing here is built.** Every requirement in
> `specs/` describes intended behavior, not behavior on `main`. Authored
> 2026-07-25 as the successor for `build-forward-platform-capabilities` task
> 4.1, per that umbrella's decision D1 (a slice must become a narrower change
> before implementation).
>
> **Archive guard — do NOT archive this change, and do NOT run
> `openspec archive demand-side-signals --yes`.** `openspec archive` syncs the
> change's delta specs into `openspec/specs/` as a side effect, and
> `openspec/specs/` is **as-built truth**. Archiving or syncing while these
> tasks are unchecked would write unbuilt behavior into canonical truth — the
> exact defect the archived `reclassify-forward-vision-specs` change removed by
> deleting eight forward-only capability directories. Sync and archive are
> §8 below and are gated on every preceding task being genuinely complete.
>
> **The umbrella's 4.1 stays unchecked until this change LANDS.** Authoring a
> successor does not complete a successor-outcome tracker; the umbrella's own
> task classification says so.

## 0. Premise verification and prerequisites

- [ ] 0.1 Before any implementation write, re-verify against `origin/main` that `openspec/specs/daemon-runtime-and-dispatch/spec.md` still states the as-built limitation that a cron schedule does NOT backfill ticks missed during downtime. If a later change already landed a catch-up policy, reclassify §2 instead of building over it.
- [ ] 0.2 Re-verify that `openspec/specs/shared-goals-and-convergence/spec.md` still describes the Goal record and its action surface as this change assumes, and that no landed change has already added standing-goal fields. Classify each task as live / landed / inverted before building.
- [ ] 0.3 Confirm `outbound-boundary-layer` has not landed inbox ingress under different field names than its `boundary-layer` delta specifies. Until it lands, implement §3 against its contract only; do not stub an inbox here.
- [ ] 0.4 Confirm the umbrella's decisions D1–D8 still hold for this slice and record any divergence as a design change here, not as silent drift.
- [ ] 0.5 Take no requirement from the host-gated open-production-commons reframe. Per umbrella D9 it is provenance only and binds nothing in either direction — "keep the reframe reachable" is not a constraint on this slice and not a review gate against it.
- [ ] 0.6 Re-read PLAN.md Scoping Rules 1, 3, and 4 as amended by the 2026-07-25 host decisions before implementing; if PR #1761 landed with different wording than this change was authored against, reconcile `design.md` D2/D5/D6 first.

## 1. Standing-goal record and execution authority

- [ ] 1.1 Add standing-goal fields to the existing Goal record — desired outcome, owning principal, universe, IANA-timezone cron-class schedule or event trigger, declared budget posture, success gates, pause state — with the next numbered storage migration. No parallel store.
- [ ] 1.2 Bind the owning principal server-side from the authenticated actor at registration and persist it as the sole execution authority.
- [ ] 1.3 Remove caller-supplied owner/actor/universe/authority resolution from the scheduled-execution path; ignore such fields and record any discrepancy with the persisted owner.
- [ ] 1.4 Remove ambient environment fallback from the scheduled-execution path; an unresolvable, revoked, paused, or under-scoped owner fails closed with a recorded reason and no host, maintainer, platform, or cached identity substitution.
- [ ] 1.5 Emit a stable `(goal_id, schedule_period)` identity for each due period, derived from durable facts and reproducible across retries, restarts, and bounded replays.
- [ ] 1.6 Adversarial tests: a forged trigger payload, an externally written scheduler row, and a set environment identity each fail to change the executing principal; a revoked owner produces a refusal rather than a fallback run.

## 2. Timezone-explicit schedules and declared missed-tick policy

- [ ] 2.1 Require a resolvable IANA timezone on every cron-class schedule at registration; refuse registration otherwise, with a reason naming the missing timezone. Never persist a row that would later evaluate in the daemon's local zone.
- [ ] 2.2 Add a per-schedule missed-tick policy (`skip` / `fire_once` / `backfill_bounded(n)`) persisted with the schedule; default existing rows to `skip` so migration changes no current behavior.
- [ ] 2.3 Apply the policy deterministically on tick-loop resume and record which policy ran and how many periods were skipped or replayed, including the count discarded beyond `n`.
- [ ] 2.4 Make a bounded replay reuse the missed period's `(goal_id, schedule_period)` identity rather than minting a new one, so the `outbound-boundary-layer` effect key deduplicates instead of double-firing.
- [ ] 2.5 Tests: downtime spanning multiple due periods resolves identically under each policy; a replayed period is byte-identical in period identity to its original; a DST transition in the goal's zone does not double-fire or skip a period.
- [ ] 2.6 Do not sync `demand-side` without the `daemon-runtime-and-dispatch` MODIFIED delta. A synced standing-goal guarantee beside an unmodified "cron ticks are silently dropped" limitation is the drift `reclassify-forward-vision-specs` removed.

## 3. Inbox consumption (schedule side only)

- [ ] 3.1 Admit each eligible inbox item into exactly one scheduled batch, evaluating the cutoff in the goal's recorded IANA timezone.
- [ ] 3.2 Record on the fired batch: the inbox receipts consumed, the cutoff instant and timezone applied, and the schedule-period identity.
- [ ] 3.3 Defer a post-cutoff item to the next period; never drop it and never back-date it into a period that already fired.
- [ ] 3.4 Make a replayed period reuse its recorded item set rather than consuming pending items belonging to a later period.
- [ ] 3.5 Own no ingress: no addressing, receipt, typing, or eligibility-cutoff definition lands here. Test that removing the boundary owner's contract makes §3 unbuildable rather than silently self-served by a local stub.

## 4. Onboarding that ends in a running goal

- [ ] 4.1 Attach two or three standing goals when an archetype path completes, with the first chosen so its gate is plausibly claimable inside week one.
- [ ] 4.2 Show the attached goal, its next scheduled action rendered in the user's own timezone, and the outcome it is designed to claim first — never an empty universe.
- [ ] 4.3 Make archetypes commons artifacts (remixable pages plus graph templates) through the canonical page and graph handles; ship a replaceable seed set, never a closed catalog, and add no archetype tool or platform archetype registry.
- [ ] 4.4 Test that an archetype authored and published by a user — not by the platform — completes onboarding with identical attachment, scheduling, and visibility behavior, and that forking a seeded archetype needs no platform approval and no code edit.

## 5. Owner-scoped demand metrics

- [ ] 5.1 Derive standing-goals-per-active-universe and weekly gate-claim counts on read from records this capability persists; add no metrics service, table of denormalized counters, or new action namespace.
- [ ] 5.2 Return them through the canonical read-only evidence handle and existing graph reads only.
- [ ] 5.3 Scope every metric to what the reading principal can already read under `identity-auth-and-access-control`; a metric never widens a counted goal's visibility.
- [ ] 5.4 Adversarial test from a principal with partial visibility: no count, label, schedule detail, or derived breakdown identifies a goal that principal cannot read directly.
- [ ] 5.5 Emit no cross-universe or published aggregate. Anything crossing a universe boundary defers to the off-by-default bucketed k-anonymized demand-signal contract owned by `paid-market-live-price-discovery`; define no second aggregation, publication, or export path.

## 6. Custody assumption and export

- [ ] 6.1 Record in the implementation (not only in `design.md`) that this lane assumes platform-held **coordination** records, and encode no assumption about where a goal's **content** lives.
- [ ] 6.2 Prove custody-agnosticism: a goal whose content resolves from a host machine, a user brain bundle, a vault, or platform storage registers, schedules, fires, and counts identically; an unreachable host yields a graceful "no host online" signal, never a fallback to a different custody mode.
- [ ] 6.3 Export every persisted coordination record — identity, schedule, timezone, trigger, pause state, gate reference, period identity, batch receipts — in a documented format sufficient to reconstruct the schedule elsewhere.

## 7. Non-monetary fence

- [ ] 7.1 Assert by test that registration, scheduling, firing, inbox consumption, onboarding attachment, and metric derivation write no escrow, fee, price, ledger, or settlement record.
- [ ] 7.2 Persist declared budget posture as a readable limit only; test that no spend path accepts posture as authorization.
- [ ] 7.3 Make a value-moving due action refuse, record the refusal, and name the required owner (`paid-market-track-e-wave-2-transport`); test that no local balance, escrow, or ledger row is written as a substitute.
- [ ] 7.4 Specify and stage nothing from umbrella tasks 4.2 (bounty posting, escrow, tranches, first-verified-claim settlement, refunds, fee/attribution) or 4.3 (measured direct-service volume gate). Those stay with the umbrella.

## 8. Acceptance, sync, and archive

- [ ] 8.1 Run focused unit, integration, and security tests for §§1–7 plus the full §14 concurrency/load matrix before treating any part as implemented.
- [ ] 8.2 Obtain opposite-provider review of the authority model (§1) and the missed-tick/replay contract (§2) before either goes live; log the verdict as a durable artifact.
- [ ] 8.3 For any public surface: live connector canary including `--assert-handles`, a real rendered chatbot conversation logged to `output/user_sim_session.md`, and freshness-stamped post-fix clean-use evidence.
- [ ] 8.4 **Gated on 8.1–8.3.** Only once every task above is genuinely complete: sync the delta specs into `openspec/specs/` and archive this change. Until then this change stays active and unsynced — see the archive guard at the top of this file.
- [ ] 8.5 **After this change lands**, check `build-forward-platform-capabilities` task 4.1 and update its slice-dependency-ledger row. Not before: authoring a successor does not complete a successor-outcome tracker.
