---
title: Loop 1 retirement roadmap - Loop 2 becomes the loop
type: plan
status: working-draft
source_issue: 958
wiki_source_path: pages/plans/loop-1-retirement-roadmap-loop-2-becomes-the-loop.md
request_kind: project-design
freshness_checked: 2026-05-21
---

# Loop 1 retirement roadmap

[[loop-2-v1-0-dgm-judgment-ran-successfully-2026-05-17]]
[[loop-2-v1-1-archive-consultation-passed-publish-gate-2026-05-17]]
[[user-buildable-community-change-loop-v0-substrate-readiness-baseline]]
[[pr-122-external-write-primitive-needed-for-user-buildable-loop-2-to]]
[[pr-123-goal-archive-with-parent-selection-turn-the-existing-set-of-]]
[[bug-083-build-branch-strict-input-isolation-false-not-honored-compil]]

## Strategic direction

Host-confirmed 2026-05-17:

**Loop 1 (`change_loop_v1`, branch `fd5c66b1d87d`, author
`mark-session`) retires once Loop 2 can own the same end-to-end loop. Loop 2,
the user-buildable family currently bound to Goal `4ff5862cc26d`, becomes the
loop.**

This is a structural commitment. PR-122, PR-123, and PR-126 are not optional
polish; they are the substrate path that lets Loop 2 replace Loop 1:

- PR-122: external-write / draft-PR emission.
- PR-123: archive query / parent-selection surface.
- PR-126: gate wiring so Loop 2 self-claims the Goal ladder and consults gate
  leaderboards.

Freshness note 2026-05-21: the original wiki source also treated BUG-083 Bug B
as an open M3 friction blocker. `origin/main` now includes PR #868 and commit
`c28bf92b` (`BUG-085: fix contradictory isolation error + seed state_schema
defaults`), so M3 is recorded below as current-code resolved pending any
live-surface retest.

## Current state - M0 achieved 2026-05-17

Loop 2 is a reasoning kernel. Loop 1 still owns execution.

Working Loop 2 lineage bound to Goal `4ff5862cc26d`:

- `ea11cb328095` v0.3 - input-blind packet-output baseline.
- `a1f5d784aaf9` v1.0 - input-aware, DGM self-judgment, judge=8/7/4,
  `safe_to_publish=false`.
- `8071e435b3ef` v1.1 - archive consultation, judge=7/5/3,
  `safe_to_publish=true`.

Loop 2 v1.1 can ingest a patch request, identify primitive gaps, consult
siblings, propose a structured patch packet, self-judge quality / novelty /
risk, select a parent, gate publish on conjunctive conditions, and emit a
next-action candidate.

Loop 2 v1.1 cannot yet open a PR, trigger checker review, pause for a human
key-turn, resume after the key-turn, merge, observe post-merge state,
reconcile wiki / issue / task / PR artifacts, run on a schedule, integrate
with the gates surface, route via the goal pool, or rely on live
state-schema-default behavior without retest evidence.

## Architecture choice - M4 resolved 2026-05-17

M4 is resolved as **Option C: gate-as-privileged-terminal-node**.

The branch is the loop, including the gate. The gate is one node in the branch,
but it is privileged at live execution time. User-built branches can include
their proposal version of the merge gate. When the branch runs for real, the
substrate swaps in the host-private version at that node. Public users see the
gate shape, can fork it, can propose amendments to their public version, and
can submit those amendments through the normal patch-request flow. Live
execution uses the host's private gate.

Default mode is a human host key-turn. Auto-fire remains a host decision.

This supersedes the older Option A / Option B framing:

- Option A, "Loop 2 reasoning plus Loop 1 execution shell", leaves execution
  outside the branch family that produced the proposal.
- Option B, "Loop 2 absorbs everything", expands the retirement into a
  multi-month substrate build.
- Option C keeps public-proposes / host-disposes intact while reusing branch
  state passing, edge sequencing, and packet emission.

Demonstration: v1.2 (`change_loop_v1_2_proposal_merge_gate_20260517`, branch
`799b50e02c09`, run `6dd1d9fce8a34cd9`, judged `4182784167984923`) includes
`merge_gate_node` as node 7. Its smoke test emitted `hold_for_host` because the
risk score was between 4 and 6. Its amendment proposals demonstrate the public
proposal path for the gate itself.

## Milestones

### M1 - Loop 2 emits real PRs

Waits on PR-122.

Capability unlocked: a `pr_emission_node` after `next_action_node`, firing
when `safe_to_publish=true` and external-write authority is available. It
emits an actual draft PR instead of only a packet that describes one.

Substrate work: implement PR-122. The primitive should accept title, body,
base branch, head branch, and labels, then return PR number and URL. It must
obey the Brain authority / idempotency model for external writes.

User-buildable work: fork v1.1 into a successor branch with the new emission
node after PR-122 lands.

Owner: dev team for substrate; Jonathan for publish approval.

### M2 - Loop 2 queries the archive

Waits on PR-123.

Capability unlocked: `archive_consultation_node` replaces hand-maintained
`known_archive` state with a live Goal archive / leaderboard query. Initial
signals can be best-effort: run count, judge scores, fork count, fork lineage
depth, last successful run recency, and a recommended parent for fork.

Substrate work: implement PR-123. Any signal that cannot be computed yet should
surface as null or omitted and become a follow-up filing rather than blocking
the first query surface.

User-buildable work: fork the current Loop 2 successor and change
`archive_consultation_node` to query rather than read static state.

Owner: dev team for substrate; Jonathan for publish approval.

### M3 - State-schema default friction drop

Current repo status 2026-05-21: current-code resolved, pending live retest.

The original blocker was BUG-083 Bug B: Loop 2 authors needed state-schema
defaults to count as effective input so defaulted fields did not force every
operator to pass every value manually. `origin/main` now includes the relevant
fix path:

- PR #868 merged: storage round-trip / Bug A path.
- `c28bf92b` landed: compiler/runtime seeding of `state_schema` defaults and
  diagnostics for missing declared inputs.

Remaining proof before treating M3 as operationally closed: run the affected
Loop 2 branch through the live surface after deploy and confirm the workaround
is no longer needed.

### M4 - Architecture decision

Resolved as Option C above. Do not reopen the old Option A / Option B framing
unless host direction changes.

### M5 - Gates wiring

Waits on PR-126.

Work after the PR-125 rescope:

1. `merge_gate_node` emits `recommended_rung_claim` using Goal
   `4ff5862cc26d`'s real ladder vocabulary:
   `learned_failure`, `pass_with_followup`, and
   `zero_required_operator_intervention_beyond_key_turn`.
2. When outcomes happen, the operator or later substrate auto-claimer calls
   `gates action=claim`.
3. `archive_consultation_node` queries `gates action=leaderboard` as a
   parent-selection signal.

This should not create a new merge-gate primitive. It wires Loop 2 against the
existing gates surface.

Owner: dev team for gates wiring; Jonathan for publish approval.

### M6 - Cutover

Migration step. Goals currently bound to Loop 1, including Goal
`c4f481e65b13` and any others found by audit, either rebind to a Loop 2
successor or are formally archived.

Cleanest path is a one-transaction substrate script that:

1. Lists all branches bound to `change_loop_v1` / `fd5c66b1d87d`.
2. For each Goal binding, records a rebind or archive decision.
3. Leaves Loop 1's branch definition discoverable for reference but unbindable
   for new work.
4. Emits a migration audit packet documenting every decision.

Optional user-buildable work: a Loop 2 branch processes the migration audit
packet into a human-readable summary.

Owner: dev team for script and migration; Jonathan for each Goal
rebind/archive approval.

## Priority order

1. PR-122 implementation - blocks M1.
2. PR-123 implementation - blocks M2.
3. PR-126 implementation - blocks M5.
4. Live retest for M3 after deploy - verifies the BUG-083 / BUG-085 path is
   operational, not just present in current code.
5. Goal-bindings migration plan - needed for M6 and designable during M1/M2.

## Gate and review contract

Code-change writers for this lane are Claude/Codex only and need an
opposite-family checker. No bounty is attached by default. If a bounty is
attached later, settlement follows the gate ladder's `bounty_requirements`.
