---
title: M6 Cutover Plan
type: plan
status: working-draft
source_issue: 985
request_id: WIKI-DOCS
wiki_source_path: pages/plans/drafts-plans-m6-cutover-retire-cheat-loop-leaderboard-driven-canonical.md
wiki_source_updated: 2026-05-21T00:00:00Z
---

# M6 Cutover Plan

**Goal:** Retire the cheat patch loop (env-var-wired `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` auto-trigger + hardcoded Loop 1 handler) and route ALL patch-request flow through Goal `4ff5862cc26d` with a **leaderboard-selected canonical handler that re-iterates automatically** as community designers publish better branches.

**Core design principle (host directive 2026-05-21):** The canonical Loop 2 handler MUST be picked by the substrate (PR-123 `recommended_parent_for_fork`), not by host gut-feel. This makes the loop self-iterating -- every time a new winner emerges on the leaderboard, the canonical handler rolls forward without manual intervention. The cutover ships the tooling AND the auto-iteration mechanism.

## Why automation over selection matters

If host picks the canonical handler manually, every iteration requires host attention. That violates the Forever Rule (24/7 with zero hosts online). If the leaderboard picks it via `recommended_parent_for_fork`, then:

- Community publishes a better branch -> it earns more runs / better judge scores / more forks -> leaderboard rank rises -> next canonical refresh swaps it in
- Host's only role is unblocking substrate gaps surfaced through filings
- The patch loop literally evolves itself, just by people using it

This is the architecture host has been pushing toward across this session: **community-build over platform-build, substrate provides selection, branches evolve**.

## Prerequisites (must be true before cutover)

1. **PR #969 (Phase 2 Slice 1) merged** -- real-PR emission authority + idempotency + consent gates land. Without this, the user-buildable loop can only emit packet-only output. Cheat loop still has real-PR capability the new loop lacks.
2. **`WORKFLOW_GITHUB_PR_CAPABILITIES` JSON map set** in production env with at least one repo destination (likely `Jonnyton/Workflow` for the dogfooding cycle).
3. **`effector_consents` row** granted via `extensions action=grant_effector_consent sink=github_pull_request destination=Jonnyton/Workflow granted_by=host` for the dogfooding destination.
4. **Dispatcher verified live.** Prior session evidence shows queued `bug_investigation` requests (`b72b6cfc-...`, `513ae266-...`, `ae896680-...`) were never claimed. Before cutover, file a fresh test bug + verify the dispatcher actually picks it up + completes a run. If broken, cheat retirement triggers an outage. Cutover blocks on this check.
5. **PR-126 gate-claim flow verified live** -- Eli's three `learned_failure` claims on 2026-05-21 prove `gates action=claim_from_branch_run` works user-side. [verified in source filing]
6. **PR-123 leaderboard live** -- `recommended_parent_for_fork goal_id=4ff5862cc26d` returns ranked entries. Just merged 2026-05-21T02:05Z. [verify deploy lands]

## The cutover (in order)

### Step 1 -- Verify dispatcher liveness

```text
extensions action=run_branch branch_def_id=<canonical_v1_1> inputs_json='{"request_text":"dispatcher liveness probe 2026-05-21"}'
```

Wait for the run to complete. If it never picks up: STOP. File a P0 substrate bug on the dispatcher before any retirement.

If healthy: proceed.

### Step 2 -- Pick canonical via the leaderboard

```text
extensions action=recommended_parent_for_fork goal_id=4ff5862cc26d
```

Returns `{branch_def_id, branch_version_id, rationale}`. **That entry becomes the canonical handler.** No host pick-by-hand.

Snapshot the result into the cutover commit message + a wiki audit note for reproducibility.

### Step 3 -- Set canonical on the Goal

```text
goals action=set_canonical goal_id=4ff5862cc26d branch_version_id=<from step 2>
```

This is the substrate-side switch. After this, any call to `goals action=run_canonical goal_id=4ff5862cc26d inputs_json=<...>` dispatches to the leaderboard's pick.

### Step 4 -- Swap file_bug's auto-trigger from cheat to canonical

In `workflow/bug_investigation.py`, change `_maybe_enqueue_investigation()` so that instead of looking up `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` (the cheat env var) and dispatching a hardcoded Loop 1 run, it does:

```text
goals action=run_canonical goal_id=4ff5862cc26d inputs_json={
  "request_text": <serialized bug filing>,
  ...
}
```

This makes `file_bug` queue investigations on the leaderboard-selected user-buildable branch, automatically.

### Step 5 -- Remove `WORKFLOW_BUG_INVESTIGATION_GOAL_ID` from production env

After Step 4 lands + deploys + a live test bug is processed successfully by the new path, the env var is no longer read. Remove it from `/etc/workflow/env` on the droplet via the existing deploy workflow.

### Step 6 -- Delete `_maybe_enqueue_investigation` cheat code path

Once Step 4 + 5 are live for ~24-48h with no regressions, delete the env-var-aware code branch entirely. Keep only the leaderboard-canonical path.

### Step 7 -- Schedule auto-iteration

Add a small cron / scheduled GH Action (or in-daemon job) that runs `recommended_parent_for_fork goal_id=4ff5862cc26d` periodically (every 6h or daily) and, if the top entry differs from the currently-canonical one, calls `set_canonical` to roll forward.

OR, simpler: add a `goal.auto_canonical_via_leaderboard: bool` flag. When true, every `goals action=run_canonical` call first re-queries the leaderboard before dispatching. Zero scheduled jobs needed; the freshest pick wins every call.

The simpler design is preferred: makes the iteration entirely substrate-resident, no scheduled-job moving parts.

## Verification protocol after cutover

**Live smoke test (real bug through the full chain):**

1. File a real test bug via `wiki action=file_bug` (e.g., a known minor bug that we want patched).
2. Observe the auto-trigger: bug_investigation request should queue with leaderboard's pick as the handler branch.
3. Wait for the run to complete (~minutes).
4. Verify the canonical branch's output produces a patch_packet attached to the bug page.
5. If Phase 2 + consent + capability are set up: verify a REAL draft PR appears on `Jonnyton/Workflow` (not just a dry-run packet).
6. Verify the branch's `recommended_rung_claim` matches a real Goal ladder rung.
7. Call `gates action=claim_from_branch_run run_id=<id>` and confirm the rung gets recorded.
8. Read the bug page to confirm the patch packet + claim are visible there.

**Post-cutover monitoring window (48-72h):**

- Watch `auto_ship_health` in `get_status` for opened-but-failed PRs from the new path.
- Watch for any `file_bug` calls that DIDN'T trigger an auto-investigation (env-var-removed-but-dispatcher-broken regression).
- Watch the leaderboard for unexpected canonical-flip behavior (a malicious or broken entry suddenly ranking #1).

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| Dispatcher broken at cutover time -> no investigations fire | Step 1 verification gates cutover; abort + file P0 if dispatcher fails |
| Phase 2 not merged -> no real-PR emission | Cutover delays until PR #969 lands |
| Leaderboard pick is a malicious / broken branch (poison-the-well attack) | Initial weights surface the rationale; auto-canonical can be turned OFF via flag. Also: branches earn rank via real runs + judge scores, which costs the attacker provider tokens. Not free to game. |
| Canonical-flip happens mid-bug | Lock canonical for the duration of an in-flight run (no swap while a run is active under the prior canonical). |
| Auto-iteration picks a poorly-tested new branch | Add a minimum-runs threshold (e.g., 5 runs) before a branch is eligible to be canonical. Quality leaderboard signals already include `completed_run_count`; just gate selection on it. |

## What this cutover DOESN'T include

- **Real-time post-merge outcome auto-claim** -- operators still have to call `claim_from_branch_run` after observing the merge. Separate slice (PR-127?).
- **Multi-Goal cutover** -- only Goal `4ff5862cc26d` (patch-loop) cuts over here. Other Goals (bug_investigation Goal `c4f481e65b13`, fantasy-writing, etc.) need their own cutovers, but the substrate they share (leaderboard + canonical + set_canonical) is the same.
- **Branch nodes calling MCP** -- PR-136 still open. Without this, archive_consultation inside a branch still needs caller-populated state. Workaround viable today; not blocking cutover.

## After M6 lands

- Loop 1 (`fd5c66b1d87d`, mark-session) becomes historical reference, not active substrate.
- Goal `4ff5862cc26d` is the canonical patch loop; the leaderboard selects who handles each request.
- Community designers can publish improved branches and watch them get promoted to canonical automatically as they earn ranks.
- The "every software project can fork our patch loop" meta-platform vision becomes real -- any project binds their own Goal to a forked version of our canonical, and their own community ranks evolves their own canonical.

**Loop 1 fully retired.** Project-internal patch loop runs on its own substrate. M6 done.

## Sequencing summary

| Step | Substrate-side | Blocker |
|---|---|---|
| Pre | PR #969 round 2 merges | Awaiting Codex round-2 |
| 1 | Dispatcher liveness probe | Verify before any teardown |
| 2 | `recommended_parent_for_fork` query | Substrate self-selects |
| 3 | `set_canonical` | One MCP call |
| 4 | `_maybe_enqueue_investigation` swap | Single PR (~half day) |
| 5 | Remove env var | Deploy-workflow change |
| 6 | Delete cheat code | After observation window |
| 7 | Auto-iteration | One flag or one cron |

**Estimate:** From PR #969 merge to fully retired = ~1-2 sessions of focused work.

## Cross-references

- `pages/plans/loop-1-retirement-roadmap-loop-2-becomes-the-loop.md` -- strategic roadmap M0-M6.
- `pages/patch-requests/pr-122-external-write-primitive-needed-for-user-buildable-loop-2-to.md` -- M1 substrate.
- `pages/patch-requests/pr-123-goal-archive-with-parent-selection-turn-the-existing-set-of-.md` -- M2 substrate (the leaderboard itself).
- `pages/patch-requests/pr-126-loop-2-branches-must-integrate-with-the-existing-gates-syste.md` -- M5 substrate.
- `drafts/notes/drafts-notes-community-onboarding-goal-4ff5862cc26d-patch-loop.md` -- community onboarding (update after cutover to reference new canonical).

_Auto-filed by wiki-change-sync from wiki page `pages/plans/drafts-plans-m6-cutover-retire-cheat-loop-leaderboard-driven-canonical.md`._
