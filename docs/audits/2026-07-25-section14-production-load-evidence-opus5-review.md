# Section 14 production-load evidence — Opus 5 review

**Date:** 2026-07-25

**Environment:** clean worktree at then-current `origin/main` `61609443`; final branch rebased before publication

**Reviewer:** Claude Opus 5, read-only peer-agent pass

**Verdict:** **ADAPT — promote now as a protocol/evidence capability only**

## Scope reviewed

The reviewer inspected `AGENTS.md`, `STATUS.md`, PLAN §14 and the API/MCP principles, the §14 idea in `ideas/INBOX.md`, the April Track J pre-draft, the 2026-07-21 concurrency/scalability audit, active OpenSpec changes with §14 tasks, and the current `tests/load/` inventory.

The host decision was applied as a hard product-ordering constraint: chatbot users through the installed connector are canonical first-class users; Agent Village is deferred and must not shape the platform or the shared load-evidence schema.

## Required adaptations

1. Use the existing lowercase terminal vocabulary `passed`, `failed`, and `not_run`.
2. Roll up required and applicable scenarios failure-first: any `failed` wins; otherwise any `not_run`; otherwise `passed`. Optional or inapplicable entries do not poison the rollup.
3. Report protocol conformance separately from scenario outcomes.
4. Keep product-surface priority in registry/roadmap ordering, not in the generic schema.
5. Centralize only the evidence/manifest layer. Capability-specific counts and thresholds are different scenarios, not duplication.
6. Require machine-readable blocking-substrate codes for `not_run`; never present `not_run` as absence of risk.
7. A mock production scenario can report `failed` when it proves a defect, or `not_run`; it can never report `passed`.
8. Mark the April pre-draft superseded as implementation authority. Retain k6 plus sidecars only as a candidate stack.
9. Establish a truthful baseline of the current single-origin system before making distributed-capacity claims.

## Approved ownership boundary

The shared `production-load-evidence` capability owns how results are recorded:

- verdict vocabulary and rollup algebra;
- versioned registry and immutable run-manifest schemas;
- environment fingerprints;
- raw metrics/trace retention and independent recomputation;
- invariant-oracle result interface;
- fault-timeline and reconciliation formats;
- baseline-comparison rules;
- blocking-substrate codes.

Capability owners retain what is exercised and how much:

- scenario definitions, workload mixes, and populations;
- absolute and comparative thresholds;
- required/optional applicability;
- substrate-driving adapters;
- invariant predicates;
- injected fault choices.

A capability §14 task may state its counts and thresholds but should reference the shared manifest schema version rather than restating the evidence field list.

## Evidence contract

Each immutable, content-addressed run pins a schema version, scenario ID/version, owning capability, verdict/reason, required blocking substrates, timestamps, exact commands, seed when applicable, operator, environment fingerprint, artifact digests, oracle outcomes, and any superseded run.

Environment evidence includes source and image identity, configuration/rollout identity, topology, region, database/pool settings, queue or Realtime tier and accepted connection envelope, participant resources, network facts, clock-sync evidence, and substrate class (`real`, `shaped`, or `mock`). It excludes secret values and private payloads.

Raw evidence must permit independent recomputation of operation counts and p50/p95/p99/max with explicit denominators. Oracles return `held`, `violated`, or `unevaluable`; an unevaluable required invariant never counts as held. Declared faults require an ordered injection/observation/recovery timeline. Reconciliation accounts for admitted, committed, claimed, delivered, and settled effects. Required baseline comparisons pin a compatible same-environment run and predeclare regression bounds.

## What can proceed now

The target OpenSpec can define the protocol, conformance requirements, blocking-substrate registry, and connector-first current-system baseline. A later dependent implementation can build the manifest validator/writer, registry loader, fingerprint collector, reconciliation generator, and conformance suite after the current `tests/load/` claim releases.

The following production scenarios remain `not_run` until their real substrates exist:

- PostgreSQL RLS/pooling/CAS/outbox;
- Realtime configured for the accepted connection envelope;
- the 500-daemon fleet fixture and operator v2 protocol;
- settlement replay and conservation primitives;
- controlled gateway/database/Realtime fault injection.

## Collision and duplication findings

`tests/load/` is actively claimed by the operator-request-trigger lane and overlaps several broader `tests/` claims, so this proposal writes nothing below `tests/`. Distributed execution also has an S11 harness/evidence-manifest task. Operator already specifies independently recomputable raw evidence and same-environment baseline rules. The shared capability must extract those cross-cutting rules without taking over either owner’s scenario.

## Promotion gate

Promote `harden-production-load-evidence` as a new target capability and leave it active and unsynced until the protocol is implemented, conformance tests pass, and at least one real adapter produces dated evidence. The drafted OpenSpec itself requires a second Opus 5 review before it becomes implementation authority.

## Draft-artifact review and adaptation

Opus 5 reviewed the complete drafted change and returned **ADAPT**. The draft correctly applied all nine first-pass adaptations but required the following before approval:

- prevent a vacuous green rollup by making an empty required/applicable set `not_run`;
- version and justify any required/optional or applicability downgrade;
- require host-authorized, bounded, provider-free live connector load with isolated identities, cleanup, abort criteria, and uptime-canary coordination;
- exclude user-authored content and pseudonymize actor/account/universe/node identifiers in raw and diagnostic evidence;
- name the exact adoption boundaries with `operator-request-trigger-contract` and `distributed-execution`;
- state that the verdict vocabulary deliberately reuses `uptime-and-alarms`;
- bind `failed` and `not_run` required rollups to the Forever Rule consequence;
- keep mock provenance visible in aggregate output;
- make supersession and idea retirement conditional on artifact-review approval.

These corrections were applied to the proposal artifacts before the final review request. The review also claimed the lane was the primary checkout; that finding was factually incorrect—the branch is in the separate `C:\Users\Jonathan\Projects\wf-full-product-next` worktree created from `origin/main`. An unrelated untracked `.codex-s14-load-verdict.md` was preserved and excluded from all commits.

The next Opus 5 pass returned **ADAPT** on one remaining taxonomy ambiguity plus implementation coverage:

- define `real`, `shaped`, and `mock` normatively, and prevent both shaped and mock runs from passing production evidence;
- replace ambiguous “production-shaped” language with declared real-substrate or real-equivalent language;
- add conformance tasks for every correction from the prior round;
- remove the undefined privacy qualifier “ordinary” rather than allowing an evidence-content escape hatch;
- make operator/distributed-execution adoption separate owner-claimed work;
- preserve the inherited 2,000-concurrent-MCP-session research target as an explicit open question;
- link the baseline-environment open question to its STATUS host-decision owner.

Those adaptations were applied before requesting the final narrow approval pass.

The narrow pass verified every prior correction and found no remaining Critical issue. It returned **ADAPT** only because three proposal/design phrases still used “production-shaped” after `shaped` became a normative non-passing substrate class. Those phrases now say “declared real substrate or real-equivalent isolated environment.” The same pass identified three missing future conformance cases—`not_run` without a blocking code, incomplete required fingerprints, and unclassified reconciliation discrepancies—which were added to task 2.3 before final approval.

## Final verdict

Opus 5 returned **APPROVE** after a final narrow recheck. It confirmed:

- zero ambiguous “production-shaped” phrases remain in the change;
- privacy rules contain no “ordinary evidence” escape hatch;
- task 2.3 covers blocking-substrate codes, complete fingerprints, and reconciliation classifications;
- strict OpenSpec validation passes and every requirement remains testable;
- the target-only proposal is safe to land active and unsynced.

Remaining observations were landing hygiene only: check tasks 1.3–1.5 with the approved effects, rebase onto current main, verify PR diff scope, and exclude unrelated untracked fleet/Codex transcript files.
