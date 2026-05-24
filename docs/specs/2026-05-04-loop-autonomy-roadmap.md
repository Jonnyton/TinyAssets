# Spec: Loop Autonomy Roadmap

Date: 2026-05-04
Request: WIKI-DESIGN / Issue #244
Builds on: `docs/milestones/auto-ship-canary-v0.md`, `docs/specs/2026-05-03-dual-key-auto-ship-acceptance.md`, PR #227 Slice C rollback spec

## Purpose

Capture the path from today's dry-run auto-ship validator to a loop that can
open PRs, wait for configured keys, merge eligible PRs, observe the result,
roll back regressions, and seek new work when the queue is empty.

This stays one roadmap entry for now because the parts are coupled. PR
creation, keyed auto-merge, ship-class graduation, branch protection,
observation, rollback, and self-seeking define one control loop. Splitting
them too early would hide the central constraint: assisted, double-keyed, and
eventually keyless ship classes must use the same loop code path.

## Current State

`docs/milestones/auto-ship-canary-v0.md` Phase 1 is dry-run only:

- `auto_ship_packet_v0` validates a packet against the safety envelope.
- Passing validation returns `would_open_pr=True`.
- The loop stops before repo writes.
- A host, dev, or contributor must notice the result and manually run the PR
  cycle.

Phase 2 and Phase 3 are already named in the milestone: Phase 2 opens a PR;
Phase 3 auto-merges canary-only PRs. This roadmap refines those phases without
changing the milestone's safety envelope.

## Destination

The destination is full loop autonomy for graduated ship classes:

- The loop opens PRs.
- The loop merges PRs.
- The loop keeps running when nobody is watching.
- The loop can generate candidate work when no users are filing requests.
- Community input remains welcome but is not required for the loop to evolve.

The mechanism should not change between dev mode and production mode:

- same PR creation call;
- same PR approval polling;
- same merge call;
- same envelope re-check immediately before merge;
- same observation and rollback hooks after merge.

Progress along the autonomy ladder happens by changing per-ship-class policy,
not by adding special-case loop branches.

## Ship-Class Ladder

Initial ladder:

1. `docs_canary`
2. `docs_general`
3. `tests_canary`
4. Later classes by explicit proposal only

Each tier adds path allowances while keeping forbidden-path defense in depth.
`docs_general` may broaden from the canary docs path to non-runtime docs.
`tests_canary` may permit narrowly allowlisted fixtures or tests. Runtime,
provider, API, wiki, dispatcher, deploy, secret, auth, and migration surfaces
remain forbidden unless a later explicit proposal creates a stricter class.

Graduation is evidence-based. A class can graduate only when all criteria hold:

- at least 10 successful auto-ships for the current class;
- at least 3 clean observation windows after those ships;
- zero rollbacks for the current class in the last 30 days;
- zero forbidden-path, symlink-bypass, envelope-bypass, or secret-like-content
  events across the class history;
- every shipped attempt has a resolvable `ship_attempt_id`, PR URL, changed
  paths list, validation result, rollback handle, and observation result;
- opposite-family review approved the graduation proposal.

Graduation means changing ship-class policy, for example allowing keys to
auto-open for `docs_canary`. It does not mean changing loop code.

## Keyed Auto-Merge

GitHub PR review state and branch protection are the canonical approval
substrate for PR-backed ships. The acceptance-key ledger remains an
observability mirror for `get_status`, wiki Investigation write-back, and
dry-run or non-PR attempts.

Default for every new ship class:

- `auto_merge=false`;
- `keys_auto_open=false`;
- required keys are `codex_reviewer` and `cowork_reviewer`;
- approvals expire after the configured TTL;
- missing approval is the safety state.

The policy format lives in `auto_ship_ship_classes.yaml`. New classes inherit
the top-level defaults unless they explicitly override them.

Auto-merge eligibility:

1. Phase 2 opens a PR through the GitHub API from an `auto-change/*` branch,
   behind a safe feature flag.
2. Branch protection requires the configured approval count and reviewer
   classes for the ship class.
3. Reviewers approve through normal GitHub PR review.
4. Phase 3 polls every open auto-ship PR.
5. The loop re-runs the safety envelope against the PR head and changed paths.
6. Eligibility is true only when the envelope still passes and either:
   `ship_class.auto_merge=true`, or all required keys are open in GitHub review
   state.
7. If eligible, the loop calls `gh pr merge` or the GitHub merge API itself.

Humans authorize while required keys are manual. The loop executes. Later
graduation flips policy so a class can auto-open keys, still through the same
poll-and-merge path.

## Failure Semantics

Failure is structural:

- if validation fails, no PR opens;
- if PR creation is disabled or fails, the attempt records the failure and the
  loop continues;
- if keys do not turn, the PR stays open;
- if branch protection or CI is red, the PR stays open;
- if the envelope fails at merge time, the PR stays open and is marked blocked;
- no separate denied state is required for missing approval.

Absence of approval is safe. The loop should continue to other work while a PR
waits.

## Branch Protection

GitHub remains the human approval substrate:

- `main` requires PR review and passing checks.
- Auto-ship branches are labeled or named so policy can map them to a
  `ship_class`.
- Required review count and accepted reviewer classes match
  `auto_ship_ship_classes.yaml`.
- Runtime/substrate classes, if proposed later, must add an explicit host key
  and cannot inherit only the two default reviewer keys.
- The loop must never merge around branch protection; it can only call GitHub's
  normal merge API and accept GitHub's refusal.

If GitHub cannot express a per-class reviewer rule directly, an Action or bot
check may translate labels into required status checks. The authoritative
approval still remains normal PR review.

## Observation And Rollback

Phase 4 of `docs/milestones/auto-ship-canary-v0.md` remains the observation
gate. Step 7's v0 signal source is wiki canary divergence:

- record `ship_status=merged`, commit SHA, rollback handle, and changed paths;
- poll the wiki canary after merge;
- compare observed state with the packet's expected canary result;
- mark divergence as `observation_gate_result=ROLLBACK_RECOMMENDED` or the
  equivalent ledger state.

Step 8 consumes the rollback primitive. Slice C is already drafted in PR #227;
implementation still needs to land. The rollback implementation must store
structured rollback PR identity (`rollback_pr_number` and `rollback_pr_url`) so
observation, auto-ship health, wiki write-back, and later attribution can agree
on which rollback happened.

Until Slice C lands, observation red opens or recommends a rollback PR rather
than claiming complete autonomous recovery.

## Empty-Queue Self-Seeking

When the work queue has been empty for a configurable threshold, a self-seeking
daemon may generate work. Simulation must use the real user path:

1. Observe that no claimable work has existed for `empty_queue_threshold`.
2. Spawn a synthetic user-sim conversation in a real chatbot surface with the
   Workflow connector installed.
3. Ask the chatbot to inspect loop state through normal MCP tools.
4. File self-improvement candidates through the same chatbot/request path that
   real users use.
5. Let those candidates enter the normal queue, review, auto-ship, and
   graduation gates.

The daemon must not file work through a privileged back channel. The test is
whether the public user path is strong enough for the loop to improve itself.

## Implementation Plan

1. Phase 2 / Step 3: loop-created PRs via GitHub API from `auto-change/*`
   branches, behind `WORKFLOW_AUTO_SHIP_PR_CREATE_ENABLED=false` by default.
2. Phase 3 / Step 4: auto-merge action that polls GitHub approval state,
   re-checks the safety envelope, checks branch protection/CI, and merges only
   when policy allows.
3. Add and wire `auto_ship_ship_classes.yaml`; all unknown/new classes inherit
   two-key manual approval by default.
4. Document and configure branch protection so GitHub PR reviews are the human
   key substrate.
5. Phase 4 / Step 7: observation poller with wiki canary divergence as v0.
6. Phase 4 / Step 8: implement Slice C rollback per PR #227, including
   structured rollback PR identity.
7. Add the empty-queue self-seeking daemon only after PR creation, keyed merge,
   observation, and rollback are proven on `docs_canary`.

## Acceptance

- The roadmap records the end-state, current state, ladder, keyed auto-merge
  mechanism, graduation criteria, failure semantics, and self-seeking behavior.
- The plan references `docs/milestones/auto-ship-canary-v0.md` Phase 2-4 and
  PR #227 Slice C rollback work.
- `auto_ship_ship_classes.yaml` defines the ship-class policy format and
  default two-key manual approval.
- Runtime implementation of PR creation and auto-merge remains feature-flagged
  and policy-driven.
- Branch protection expectations are explicit.
- Empty-queue self-seeking files through the real chatbot/user-sim path.

## Deferred

Drift-from-project-goals resilience is real but intentionally deferred to a
later milestone. This roadmap is about loop mechanics and safety gates, not
long-horizon goal alignment.
