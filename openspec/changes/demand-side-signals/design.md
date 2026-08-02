## Context

`build-forward-platform-capabilities` task 4.1 is a successor-outcome tracker that this change now owns — assigned 2026-07-25, unlanded, and deliberately still unchecked in the umbrella, because a successor-outcome tracker completes when its successor *lands*, not when it is authored. Its own note explains why it is the cheapest slice to promote: unlike 4.2 and 4.3 it is **not** blocked on the money transport — umbrella D3 names price, forward, training, data, pool, and hardware as transaction consumers, and standing-goal / onboarding work is none of them. Its real prerequisites are `outbound-boundary-layer` for inbox ingress, `daemon-runtime-and-dispatch` for the heartbeat, and `shared-goals-and-convergence` for the Goal primitive.

The shipped substrate is close enough to be misread as sufficient. `shared-goals-and-convergence` gives Goals a stable id, an author, a SQLite home, binding, protocols, gate ladders, and gate claims. `daemon-runtime-and-dispatch` gives a persisted cron/interval scheduler with per-subscription event idempotency and owner-gated removal. What is missing is the join: no record binds a Goal to a timezone-explicit schedule, a budget posture, and a pause state as one durable demand object, and the scheduler's own canonical text says cron ticks missed during downtime are dropped. A standing goal is exactly the case where those gaps compound, because its defining property is that it runs while nobody is watching — and it is also the case where the project's live authority findings bite hardest (D3).

This change is authored against PLAN.md as of the 2026-07-25 host decisions (PR #1761, open at authoring time — read from the PR, not from `origin/main`, which still predates it). Where those positions bear on this design they are cited by rule, not paraphrased into new policy.

## Goals / Non-Goals

**Goals:**

- Make a standing goal a durable object that keeps producing demand with zero sessions open and zero hosts online, per the Forever Rule.
- Bind execution authority to the persisted record so an absent owner's goal cannot be steered, impersonated, or silently escalated to a host identity.
- Make the schedule honest about time: an explicit IANA zone, and a declared answer for periods missed during downtime.
- End onboarding in operational state rather than an empty universe, using commons artifacts the community can replace.
- Give the leading demand metric a home that leaks nothing and publishes nothing by default.

**Non-Goals:**

- Any monetary surface. Bounties, escrow, tranches, fees, settlement, and the measured direct-service gate stay with umbrella tasks 4.2/4.3.
- Inbox addressing, ingress, receipt, or typing — those belong to `outbound-boundary-layer`.
- A published or cross-universe demand aggregate — that is `paid-market-live-price-discovery`'s off-by-default k-anonymized signal.
- Answering the open private-data custody question, in either direction.
- Any new top-level MCP handle (see D2).
- Declaring 4.1 complete by landing this change. Per the umbrella's own promotion convention, 4.1 is completed by this successor **landing**, not by its authoring.

## Decisions

### D1 — Scope is the non-monetary half of `demand-side`, and the split is by requirement

The umbrella's `demand-side` delta held five requirements. Two are non-monetary and move here; three are money or gated on a product parameter and stay. The split is recorded as a **partial release**: the umbrella's release convention (tasks 1.1/1.2/2.1) is that a released delta has exactly one active successor owner, and physically moving rather than copying is what enforces it. Copying the two requirements would have created two active owners of the same text — the defect task 1.2 explicitly called out. So they were moved, and the `demand-side` capability now has two owners split disjointly **by requirement**, which preserves the invariant the convention exists to protect.

### D2 — No new top-level primitive; every behavior lands under the seven canonical handles

PLAN.md Scoping Rule 1, as amended by the host-approved 2026-07-25 irreducibility finding, is the governing rule: a new top-level primitive ships **only** on a recorded finding that the behavior has essentially one working useful shape. The corollary is the operative half here — a behavior with many plausible custom shapes is user-buildable by definition and belongs to the commons. No irreducibility finding is recorded for anything in this change, so nothing here ships as a handle. The calls made:

| Umbrella text that could read as a new tool | Irreducibility call | Where it lands |
|---|---|---|
| A standing goal as a new substrate object | **Not irreducible.** A standing goal is `Goal` + `Trigger` — both are already canonical work concepts in PLAN.md § *Canonical Vocabulary*, whose six base concepts include `Trigger`: "the event or schedule that asks the platform to start, resume, replay, or route work." Nothing about "a goal with a schedule" is a new kind of thing. | Fields and actions on the existing Goal record, dispatched through the existing `goals` action table (see the surface note below); execution via the canonical run handle. |
| Inbox scheduling as a `schedule` or `inbox` tool | **Not irreducible**, and split-owned. Ingress is `outbound-boundary-layer`'s; the consuming schedule is a field set and four actions on the goal record. | `set_schedule` / `clear_schedule` / `pause` / `resume` on the existing `goals` table; ingress stays with the boundary owner. |
| Per-universe operational metrics as a metrics/dashboard surface | **Not irreducible.** Metrics are derived read-only evidence over records we already hold — the definition of what the read-only evidence handle is for. | `get_status` for universe-scoped evidence; `read_graph` for goal-scoped counts. |
| Archetype onboarding as a platform archetype catalog | **Not irreducible — and the corollary applies directly.** "What should a starter archetype look like" has many plausible shapes, so it is user-buildable by definition and belongs to the commons, exactly as brain organization does under the 2026-07-25 decision. | Archetypes are commons pages + graph templates via `read_page` / `write_page`; the platform ships a replaceable seed set only. |
| The proactivity heartbeat executing due work | **Already shipped substrate**, not a new primitive. But the missed-tick gap is a genuine structural gap: no composition of existing primitives can recover a tick the scheduler never recorded as due. | A MODIFIED delta on `daemon-runtime-and-dispatch`, not a new tool. |

**Surface note — the Goal action table is fixed, so extending it is a MODIFIED delta.** "Lands under a canonical handle" is necessary but not sufficient. The as-built `shared-goals-and-convergence` requirement specifies one `goals` tool dispatching a **fixed** table of named actions and enumerates that table; adding `set_schedule`, `clear_schedule`, `pause`, and `resume`, plus standing-goal fields on the Goal record, changes that requirement. Asserting those additions only in the `demand-side` delta would leave canonical truth describing a table that no longer matches — silent drift, and the worst defect class in this repo. So the extension is carried as a MODIFIED delta on `shared-goals-and-convergence`, and `demand-side` may not sync without it. The irreducibility call is unchanged by this: extending a fixed table under an existing handle is still not a new top-level primitive.

The seed-set-not-catalog shape follows the pattern PLAN.md's 2026-07-25 privacy decision names explicitly: `_WIKI_CATEGORIES` seeds a vocabulary while custom values are sanitized and accepted. The test it gives — *can a user replace or extend it without asking us?* — is satisfied for archetypes, which is why they are commons content and not platform code.

### D3 — Authority comes from the persisted record, and the failure mode is closed

This is the single highest-risk requirement in the change, because a standing goal's defining property is that it acts while its owner is absent. The as-built scheduler contract in `openspec/specs/daemon-runtime-and-dispatch/spec.md` establishes persistence, per-subscription event idempotency, per-owner rate limits, and owner-gated *removal* — but it says nothing about where the *executing* identity comes from, which is precisely the gap a standing goal walks into.

Two findings outside the spec files make the risk concrete rather than theoretical. **Both are cited here as filed concerns to be re-verified against code before implementation, not as facts this design proves.** (1) The `STATUS.md` Concern filed 2026-07-25: "Scheduler trusts client-supplied `owner_actor`, no caller binding or branch-authority check (`runtime_ops.py:350-392`, legacy-reachable)". (2) The `STATUS.md` Concern filed 2026-06-30 / verified 2026-07-22: the `_current_actor` env fallback at `engine_helpers.py:192` bypasses `permissions.py`. Task 0.7 re-verifies both before §1 is built; if either has since been fixed, the corresponding refusal is a regression guard rather than a fix, which is still worth specifying but should be labelled honestly.

The requirement is therefore written as three separate refusals — caller-supplied fields, externally-written scheduler rows, and ambient environment fallback — because these are three distinct bypass shapes and a single "derive from the record" sentence tends to close only the first. Fail-closed is the default and the escalation path is nothing: not host, not maintainer, not a cached prior identity.

### D4 — Missed ticks are declared, not silent, and a replay reuses its period identity

The canonical scheduler text is explicit that a cron schedule "does NOT backfill cron ticks missed while the daemon was down". For a chat-triggered branch that is a tolerable limitation. For a standing goal it is the whole failure mode: the owner is absent by design, so a lost week is invisible to the only person who would notice.

The fix is not "always backfill" — that turns a two-week outage into a two-week thundering herd, and for an outbound-effecting goal into two weeks of duplicated external effects. It is a **declared** policy per schedule (`skip` / `fire_once` / `backfill_bounded(n)`), recorded with what it actually did. The bounded-replay clause carries the load-bearing detail: a replayed period reuses the missed period's `(goal_id, schedule_period)` identity rather than minting a new one. That is not incidental — `outbound-boundary-layer`'s effect key is specified as derived from "durable goal, schedule-period, and item-fingerprint inputs", so a replay that mints a fresh period identity would defeat the deduplication its owner is building. Producing a stable period identity is this change's half of that contract.

Because the declared policy contradicts a canonical as-built limitation, it is carried as a MODIFIED delta on `daemon-runtime-and-dispatch` rather than asserted in the `demand-side` delta alone. An active change's delta describes post-change behavior and alters nothing canonical until sync, so it is safe to hold now, and holding it is what keeps the supersession from being a promise nobody is obliged to keep — the reasoning `outbound-boundary-layer` used for the same situation.

### D5 — Metrics are derived, scoped, and publish nothing

Two constraints shape this. First, privacy posture: `paid-market-live-price-discovery` already owns a demand signal that is `TINYASSETS_DEMAND_SIGNAL=off` by default and, when enabled, emits only a coarse daily bucketed k-anonymized per-capability signal with no identifiable universe, organization, goal, prompt, dataset, or private workload facts. Defining a second aggregation path here would fork that posture, so this change defines none and defers to that owner for anything crossing a universe boundary. Second, leakage: there is a live P1 finding that branch reads leak restricted wiki path, title, and summary through a related-pages field — a metric that counts restricted goals is the same defect class one step removed, so the requirement forbids counts, labels, and derived breakdowns that would identify a goal the reader cannot read, not just direct field exposure.

Per PLAN.md Scoping Rule 3 as amended 2026-07-25, that is the correct division: guidance about what to keep private is commons content, but a boundary a user must not be able to move is enforcement, and enforcement is platform code. Visibility scoping on metrics is enforcement.

### D6 — Name the custody assumption; answer nothing

PLAN.md Scoping Rule 4 was reopened on 2026-07-25: private-data custody is a scoped **open research question**, per-situation and user-chosen among host machine, private universe brain, vault, and platform-held, with none ruled in or out. The instruction to a lane is exact — do not encode either answer as settled, name the custody mode your lane assumes, scope the lane to it, and record the assumption.

This is compliance, not scope expansion. Scoping Rule 4 obliges *every* lane touching private data to name its custody mode and record the assumption; a lane that stays silent is the thing the rule forbids. The requirement binds only records this change already persists under task 4.1's scope and adds no product capability — which is why it lives here rather than becoming its own change.

This lane's assumption: **coordination records are platform-held** — goal identity, schedule, timezone, trigger, pause state, gate reference, period identity, batch receipts, counts. That is stated, not implied. What the lane deliberately does *not* assume is anything about the **content** a standing goal reads or produces; a goal whose content is host-resident, brain-bundle-resident, vault-held, or platform-held schedules and counts identically. The async-availability allowance already in Scoping Rule 4 covers the host-resident case: an unreachable host yields a graceful "no host online" signal rather than a silent fallback to a different custody mode. The exportability requirement is the same rule's no-lock-in obligation applied to this lane's own records.

### D7 — The money edge refuses rather than degrades

Umbrella D3 requires all value movement to converge on one authenticated transaction boundary; task 4.1's note confirms standing-goal work is not one of its consumers. The risk is not that this change deliberately builds a payment surface — it is that "declared budget posture" drifts into "spend authorization", or that a due action quietly writes a local balance row because the transport does not exist yet. Both are how a second accounting path gets born. So budget posture is specified as a recorded *limit* enforced by whoever performs the spend, and a value-moving due action **refuses and names its required owner** rather than degrading to a best-effort local debit.

### D8 — Umbrella D9 binds nothing here

Per umbrella D9, the 2026-07-19 open-production-commons reframe is provenance only and non-normative in both directions. No requirement in this change is taken from it, and nothing here is designed, blocked, or reviewed *for* it. "Keep the reframe reachable" is not a constraint on this slice and is not grounds for rejecting this design.

## Dependency boundaries

| This change | Depends on | Why the edge exists |
|---|---|---|
| Standing-goal record | `shared-goals-and-convergence` | The Goal primitive, its id, author, catalog home, and gate ladder already exist; a standing goal is fields and lifecycle on that record, not a parallel object. |
| Execution authority | `identity-auth-and-access-control` | The authenticated principal bound at registration and the visibility/ownership axes are that capability's; this change consumes them and adds no actor model. |
| Heartbeat and schedule | `daemon-runtime-and-dispatch` | The persisted scheduler and the dispatch cycle are shipped; this change adds the timezone and missed-tick contract as a MODIFIED delta. |
| Inbox batching | `outbound-boundary-layer` (unbuilt) | That owner defines addressing, ingress, receipt, typing, and cutoff; this change owns only the consuming schedule. Implementable against its contract, not against a live inbox. |
| Gate claims for onboarding outcomes | `constraint-evaluation`, `evaluation-outcomes-and-attribution` | The week-one "felt win" is a gate claim; gate evaluation and claim ordering are not redefined here. |
| Any value movement | `paid-market-track-e-wave-2-transport` (unbuilt) | Umbrella D3's single money transport. This change refuses at the edge instead of consuming it. |
| Published demand aggregates | `paid-market-live-price-discovery` (unbuilt) | Owner of the off-by-default k-anonymized demand signal. No second path here. |
| Bounties, direct-service gate | `build-forward-platform-capabilities` tasks 4.2 / 4.3 | Retained by the umbrella; out of scope by D1 of this change. |

## Risks / Trade-offs

- [Risk] A partial capability release is a new pattern and could be read as two owners of one delta. → The split is disjoint **by requirement** and stated in both the proposal and the umbrella's own 4.1 note; the umbrella's remaining three requirements are named explicitly so no reader has to infer the boundary.
- [Risk] "Standing goal" grows into a new primitive by accretion. → D2 records the irreducibility call per behavior; any future field that cannot be expressed under the seven canonical handles is the signal to stop and record an irreducibility finding, not to add a handle.
- [Risk] Bounded backfill duplicates external effects. → Replay reuses the missed period's identity, which is exactly the input `outbound-boundary-layer`'s effect key is specified to derive from. The two owners must be tested together; until the boundary owner lands, replay is verifiable only against its contract.
- [Risk] The metric surface leaks restricted goals through counts. → The requirement forbids identifying breakdowns, not merely direct fields, and the acceptance tasks include an adversarial read from a principal with partial visibility.
- [Risk] Budget posture drifts into spend authority. → Specified as a recorded limit with an explicit refusal scenario; the acceptance task asserts no spend path accepts posture as authorization.
- [Trade-off] Requiring an IANA timezone at registration rejects schedules that would previously have been accepted. → Deliberate. Silent local-zone evaluation is the failure this requirement exists to remove, and the rejection is at registration where a human is present, not at fire time where nobody is.

## Migration Plan

1. Add the standing-goal fields and their storage migration on the existing Goal record; no parallel store.
2. Bind the owning principal server-side at registration and route heartbeat execution through it; remove caller-supplied and ambient owner resolution on that path.
3. Add the required IANA timezone and the declared missed-tick policy to the scheduler, defaulting existing rows to `skip` so behavior is unchanged until an owner declares otherwise.
4. Add period identity and batch-receipt recording; hand the identity to the boundary owner's effect-key contract when it lands.
5. Seed replaceable commons archetypes and the onboarding attachment path; verify a non-platform-authored archetype completes onboarding.
6. Add derived metrics on the read-only evidence surface with visibility scoping and an adversarial partial-visibility test.
7. Only then run focused tests, the §14 concurrency/load matrix, canaries, rendered chatbot acceptance, and post-fix clean-use evidence.

Rollback is per step: schedules default to `skip` (the current behavior), metrics are read-only and removable, and archetypes are commons content. The storage migration for the standing-goal fields is the only step needing a tested rollback plan.

## Open Questions

- What default missed-tick policy should a *new* standing goal carry? `skip` is the safe migration default for existing rows, but it is arguably the wrong default for a goal whose entire purpose is running unattended.
- What bound `n` is sane for `backfill_bounded`, and is the bound per-schedule or platform-capped?
- Which seed archetypes ship, and who curates the seed set as commons archetypes accumulate? (Curation policy, not a spec question — but it decides what a new founder sees first.)
- Where does a standing goal's *content* resolution live for each custody mode? Scoped out of this lane deliberately per D6; it needs the custody research to progress before it can be specified anywhere.
