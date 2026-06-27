# GitHub-Aligned Worktree Discipline (full procedure)

> **Canonical full procedure.** Moved out of `AGENTS.md` on 2026-06-25 under
> [ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md): the
> detailed step-by-step procedure is pointer-loaded *reference*, not every-turn
> static context. `AGENTS.md` §"GitHub-Aligned Worktree Discipline" keeps the
> load-bearing invariants inline + a pointer here. The `git-workflow-and-versioning`
> skill summarizes this for on-demand git work and points here as canonical.

GitHub is the integration model. A TinyAssets worktree is the local checkout
for one Git branch; the branch folds back through a PR; `STATUS.md` is the
claim surface, not a replacement for GitHub history. A branch by itself is
not durable memory. It remembers commits, not why the branch exists, whether
it is live-safe, what blocks it, what ideas are parked in it, who owns it, or
whether it should merge, split, be abandoned, or become a PR. Uncommitted
changes are weaker: they exist only in that local worktree. The durable memory
layer is `_PURPOSE.md`, `.agents/worktrees.md`, `STATUS.md`, idea files, and
draft PR bodies.

Every branch/worktree must be in exactly one lane state:

- **Active lane**: actionable now. Has a `STATUS.md` row with exact Files /
  Depends / Status ownership, a local worktree path, a branch, and
  `_PURPOSE.md`.
- **Parked draft lane**: not necessarily actionable now. Has a pushed branch
  and draft PR. The PR body or `_PURPOSE.md` records ship condition, abandon
  condition, blockers, review gates, memory refs, related implications, and
  pickup hints.
- **Idea/reference only**: no build authority. Captured in `ideas/INBOX.md`,
  `ideas/PIPELINE.md`, or the bottom "Idea feed refs" section of
  `_PURPOSE.md`. It must be promoted into `STATUS.md` and checked against
  `PLAN.md` before implementation.
- **Abandoned/swept**: worktree removed or marked abandoned in
  `.agents/worktrees.md` with a reason. Useful ideas are extracted before
  deletion.

`worktree_status.py` emits more diagnostic states than the four canonical
lane states. `ACTIVE_LANE` and `PARKED_DRAFT` map directly to canonical lane
states. `DIRTY_*`, `IN_FLIGHT*`, `NEEDS_*`, `PURPOSE_INCOMPLETE`, `ORPHANED`,
`MISSING`, and `READY_TO_REMOVE` are action-required intermediate states that
must be fixed, promoted, parked, or swept before the branch is considered
durably remembered. `Idea/reference only` has no worktree state because it
lives in `ideas/*.md` or bottom-of-lane "Idea feed refs", not in a checkout.

Branch-selector safety rule: a non-main branch is isolated from the live
deploy chain until merged to `main`. Merging to `main` is production-impacting
for the live MCP/backend deploy chain and must pass the relevant gates.
Switching a dirty checkout to `main` is unsafe because it can drag branch
changes into main or confuse what is live-safe. For new live-ready work, start
a clean session/worktree from `main`. Leaving a branch as-is is safe only when
the lane has durable metadata; otherwise it is forgotten-work risk.

When creating a worktree:

1. Use a purpose-named branch (`codex/<slug>`, `claude/<slug>`,
   `cursor/<slug>`, `fix/<slug>`, `chore/<slug>`, etc.).
2. Use a sibling path `../wf-<slug>` unless an existing manager names it
   differently. Avoid `TinyAssets-foo`, nested `TinyAssets/foo`, and hash-only
   names for new work.
3. Create `_PURPOSE.md` at the worktree root, <=30 lines: purpose,
   provider/session, branch, base ref, STATUS row / PR / issue, relevant
   PLAN module refs, ship condition, abandon condition, pickup hints, memory
   refs, related implication refs, and a bottom "Idea feed refs" section for
   loose ideas that must not be forgotten but are not build authority.
4. Append a create event to `.agents/worktrees.md`; append a remove event
   when the PR lands or the lane is abandoned.
5. Run `python scripts/worktree_status.py` at session start or before a
   cleanup pass to find pickup-ready, stale, orphaned, or dirty worktrees.

Memory refs are required for inherited work. When a worktree continues,
reviews, or builds on work from another provider/family, `_PURPOSE.md`,
`.agents/worktrees.md`, the STATUS row, or the PR body must reference the
preceding provider's durable memory/artifact paths, for example
`.claude/agent-memory/navigator/2026-05-02-worktree-discipline-design.md`.
Before coding, the pickup provider reads those memories plus the source
artifact and records any new memory refs it creates. If no memory path is
listed, search `.claude/agent-memory/`, `.agents/activity.log`, recent audit
artifacts, and branch/PR notes by task slug before assuming context is absent.

Related implications stay live across the whole GitHub/worktree lifecycle.
At planning, build, review, and fold-back, re-check the relevant `PLAN.md`
modules as the project/module understanding. Also re-check linked `STATUS.md`
lanes, `ideas/PIPELINE.md` rows, research artifacts, design notes, and memory
refs that touch the same files, primitives, user surfaces, or review gates.
`ideas/INBOX.md` captures are not design truth or build authority; copy them
into the bottom "Idea feed refs" area of the worktree/PR when they are useful
reminders. If a related implication changes the approach, update the STATUS
row and PR body before continuing; if it does not apply, record that in the PR
or handoff.

Review-blocked work still gets a lane. If a finding needs opposite-provider
review, create the review row as claimable and create/reserve the
implementation row as `pending` with `Depends` naming the review artifact and
required verdict. The worktree/branch may exist before review, but runtime
implementation, push, live rollout, and acceptance-test advancement stay
blocked until the review returns `approve` or `adapt`. If a branch has enough
metadata to push, use a draft PR or clearly blocked PR body rather than an
untracked private branch.

Legacy coordination docs (`ideas/PIPELINE.md`, `ideas/INBOX.md`,
`docs/vetted-specs.md`, `docs/exec-plans/active/*`, old audit docs, and
agent memories) are context, not build queues. Before building from any of
them, promote/refactor the work into current project state:

- re-check relevant `PLAN.md` modules as design truth, plus `STATUS.md`,
  `ideas/PIPELINE.md`, recent commits, and active research gates;
- create or update a `STATUS.md` Work row with exact Files, Depends, Status,
  proposed branch, proposed worktree path, PR/fold-back expectation, and
  PLAN module refs, prior-provider memory refs, and related implication refs;
- carry `ideas/INBOX.md` captures only as bottom-of-lane "Idea feed refs" so
  promising ideas are not forgotten, never as permission to build;
- run `claim_check.py --check-files` before broadening Files;
- only then claim and build in the worktree.

Existing worktrees are retrofit-on-next-touch: add `_PURPOSE.md` and inventory
events when you next work there. Do not bulk rewrite another provider's active
worktree metadata unless the STATUS row or owner asks for it.

## Branch & worktree lifecycle automation

The branch/worktree hygiene that prevented the "1,209 behind / 600+ branches"
drift is automated, not a manual ritual to remember. Design note:
`docs/design-notes/2026-06-24-branch-lifecycle-automation.md`. Four layers:

- **Layer 0 — table stakes.** Repo setting `delete_branch_on_merge=true` (GitHub
  auto-deletes a PR's head branch on merge) plus `fetch.prune`/`rerere`. Apply
  on any machine with `python scripts/setup_git_hygiene.py`.
- **Layer 1 — `scripts/branch_janitor.py`.** Classifies every remote branch
  PROTECTED / ACTIVE / MERGED / STALE_FLAG / STALE_DELETE. Default mode reports
  only; `--apply` deletes MERGED (already on main) + STALE_DELETE. Hard
  guardrails: never deletes main/release, open-PR branches, or commits < 7d.
  Driven by `.github/workflows/branch-janitor.yml` (daily `apply-all`,
  self-maintaining; manual `workflow_dispatch` with `report` / `apply-merged`
  / `apply-all`, where `report` is an on-demand dry-run).
- **Layer 2 — `python scripts/wt.py new|done|list`.** One command for both
  halves of the loop: `new` creates a worktree off `origin/main` + scaffolds
  `_PURPOSE.md`; `done` verifies the branch merged before removing the worktree
  and branch (refuses unmerged unless `--force`). Use it instead of raw
  `git worktree add`/`remove` so teardown stops being optional.
- **Layer 3 — `scripts/session_sync_gate.py`.** Session-start step 0 (fetch
  `--prune` + warn if the primary checkout is off `main` or behind origin/main).
