---
name: git-workflow-and-versioning
description: Structures git workflow practices. Use when making any code change. Use when committing, branching, resolving conflicts, or when you need to organize work across multiple parallel streams.
---

# Git Workflow and Versioning

## Overview

Git is your safety net. Treat commits as save points, branches as sandboxes, and history as documentation. With AI agents generating code at high speed, disciplined version control is the mechanism that keeps changes manageable, reviewable, and reversible.

## When to Use

Always. Every code change flows through git.

## Core Principles

### Trunk-Based Development (Recommended)

Keep `main` always deployable. Work in short-lived feature branches that merge back within 1-3 days. Long-lived development branches are hidden costs — they diverge, create merge conflicts, and delay integration. DORA research consistently shows trunk-based development correlates with high-performing engineering teams.

```
main ──●──●──●──●──●──●──●──●──●──  (always deployable)
        ╲      ╱  ╲    ╱
         ●──●─╱    ●──╱    ← short-lived feature branches (1-3 days)
```

This is the recommended default. Teams using gitflow or long-lived branches can adapt the principles (atomic commits, small changes, descriptive messages) to their branching model — the commit discipline matters more than the specific branching strategy.

- **Dev branches are costs.** Every day a branch lives, it accumulates merge risk.
- **Release branches are acceptable.** When you need to stabilize a release while main moves forward.
- **Feature flags > long branches.** Prefer deploying incomplete work behind flags rather than keeping it on a branch for weeks.

### 1. Commit Early, Commit Often

Each successful increment gets its own commit. Don't accumulate large uncommitted changes.

```
Work pattern:
  Implement slice → Test → Verify → Commit → Next slice

Not this:
  Implement everything → Hope it works → Giant commit
```

Commits are save points. If the next change breaks something, you can revert to the last known-good state instantly.

### 2. Atomic Commits

Each commit does one logical thing:

```
# Good: Each commit is self-contained
git log --oneline
a1b2c3d Add task creation endpoint with validation
d4e5f6g Add task creation form component
h7i8j9k Connect form to API and add loading state
m1n2o3p Add task creation tests (unit + integration)

# Bad: Everything mixed together
git log --oneline
x1y2z3a Add task feature, fix sidebar, update deps, refactor utils
```

### 3. Descriptive Messages

Commit messages explain the *why*, not just the *what*:

```
# Good: Explains intent
feat: add email validation to registration endpoint

Prevents invalid email formats from reaching the database.
Uses Zod schema validation at the route handler level,
consistent with existing validation patterns in auth.ts.

# Bad: Describes what's obvious from the diff
update auth.ts
```

**Format:**
```
<type>: <short description>

<optional body explaining why, not what>
```

**Types:**
- `feat` — New feature
- `fix` — Bug fix
- `refactor` — Code change that neither fixes a bug nor adds a feature
- `test` — Adding or updating tests
- `docs` — Documentation only
- `chore` — Tooling, dependencies, config

### 4. Keep Concerns Separate

Don't combine formatting changes with behavior changes. Don't combine refactors with features. Each type of change should be a separate commit — and ideally a separate PR:

```
# Good: Separate concerns
git commit -m "refactor: extract validation logic to shared utility"
git commit -m "feat: add phone number validation to registration"

# Bad: Mixed concerns
git commit -m "refactor validation and add phone number field"
```

**Separate refactoring from feature work.** A refactoring change and a feature change are two different changes — submit them separately. This makes each change easier to review, revert, and understand in history. Small cleanups (renaming a variable) can be included in a feature commit at reviewer discretion.

### 5. Size Your Changes

Target ~100 lines per commit/PR. Changes over ~1000 lines should be split. See the splitting strategies in `code-review-and-quality` for how to break down large changes.

```
~100 lines  → Easy to review, easy to revert
~300 lines  → Acceptable for a single logical change
~1000 lines → Split into smaller changes
```

## Branching Strategy

### Feature Branches

```
main (always deployable)
  │
  ├── feature/task-creation    ← One feature per branch
  ├── feature/user-settings    ← Parallel work
  └── fix/duplicate-tasks      ← Bug fixes
```

- Branch from `main` (or the team's default branch)
- Keep branches short-lived (merge within 1-3 days) — long-lived branches are hidden costs
- Delete branches after merge
- Prefer feature flags over long-lived branches for incomplete features

### Branch Naming

```
feature/<short-description>   → feature/task-creation
fix/<short-description>       → fix/duplicate-tasks
chore/<short-description>     → chore/update-deps
refactor/<short-description>  → refactor/auth-module
```

## Working with Worktrees

For parallel AI agent work, use git worktrees to run multiple branches simultaneously:

```bash
# Create a worktree for a feature branch
git worktree add ../project-feature-a feature/task-creation
git worktree add ../project-feature-b feature/user-settings

# Each worktree is a separate directory with its own branch
# Agents can work in parallel without interfering
ls ../
  project/              ← main branch
  project-feature-a/    ← task-creation branch
  project-feature-b/    ← user-settings branch

# When done, merge and clean up
git worktree remove ../project-feature-a
```

Benefits:
- Multiple agents can work on different features simultaneously
- No branch switching needed (each directory has its own branch)
- If one experiment fails, delete the worktree — nothing is lost
- Changes are isolated until explicitly merged

### Workflow Project Worktree Discipline

For this repo, conform to GitHub's branch/PR model:

- One buildable work item maps to one Git branch, one local `../wf-<slug>`
  worktree, and one PR or draft PR when pushed.
- `STATUS.md` is the claim and collision surface. GitHub is the durable
  branch, commit, review, and merge surface.
- Branches are not memory. A branch remembers commits, not why the lane
  exists, whether it is live-safe, what blocks it, what ideas are parked in it,
  who owns it, or whether it should merge, split, be abandoned, or become a
  PR. `_PURPOSE.md`, `.agents/worktrees.md`, `STATUS.md`, idea files, and
  draft PR bodies are the memory layer.
- Every branch/worktree is one of four states:
  - Active lane: actionable now; has a `STATUS.md` row with exact Files /
    Depends / Status, a branch, local worktree path, and `_PURPOSE.md`.
  - Parked draft lane: pushed branch + draft PR; PR body or `_PURPOSE.md`
    records ship/abandon condition, blockers, review gates, memory refs,
    related implications, and pickup hints.
  - Idea/reference only: captured in `ideas/INBOX.md`, `ideas/PIPELINE.md`, or
    bottom "Idea feed refs"; not build authority until promoted into
    `STATUS.md` and checked against `PLAN.md`.
  - Abandoned/swept: worktree removed or logged abandoned in
    `.agents/worktrees.md`; useful ideas extracted first.
- Every new worktree gets `_PURPOSE.md` at its root. See `AGENTS.md`
  §"GitHub-Aligned Worktree Discipline" for the canonical 12-field template.
- Append create/remove/sweep events to `.agents/worktrees.md`.
- Run `python scripts/worktree_status.py` at session start to see active lanes,
  parked drafts, dirty current checkouts, missing/incomplete `_PURPOSE.md`,
  orphaned/missing paths, and PR/STATUS promotion gaps.
- Run `python scripts/provider_context_feed.py --provider <provider> --phase <claim|plan|build|review|foldback|memory-write>`
  at every lifecycle checkpoint where work narrows or advances. This catches
  Claude/Codex/Cursor/shared memories, loose ideas, research artifacts,
  provider automation notes, and worktree handoffs that should feed the lane.
  Phase filters are coarse triage; use `--limit 10` for compact hook-like
  output and a larger limit when auditing whether a category is absent.
- When taking over work, read memory refs from `_PURPOSE.md`,
  `.agents/worktrees.md`, the STATUS row, and the PR body before coding. If
  none are listed, search `.claude/agent-memory/`, `.agents/activity.log`,
  recent audit artifacts, and branch/PR notes by task slug.
- Cross-consider related implications at planning, build, review, and
  fold-back. Relevant `PLAN.md` modules are the project/module understanding
  and must be reviewed for the lane. Related `STATUS.md` lanes,
  `ideas/PIPELINE.md` rows, research artifacts, design notes, or memory refs
  stay live context until the PR folds back or the lane is explicitly
  rejected/deferred. `ideas/INBOX.md` captures are only idea-feed reminders;
  carry them at the bottom of the lane when useful, but do not treat them as
  design truth or build authorization.
- Review-blocked ideas still get a branch/worktree lane. Keep the row
  `pending` with Depends naming the review artifact/verdict; do not advance
  runtime implementation, push, live rollout, or acceptance-test claims until
  review returns `approve` or `adapt`.
- Branch-selector safety: a non-main branch is isolated from live deploy until
  merged to `main`; merging to `main` affects the live MCP/backend deploy
  chain and requires the right gates. Do not switch a dirty checkout to `main`.
  Start a clean session/worktree from `main` for new live-ready work. Leaving a
  branch parked is safe only when it has durable lane metadata.

Legacy planning docs (`ideas/PIPELINE.md`, `docs/vetted-specs.md`,
`docs/exec-plans/active/*`, old audits, and agent memories) are context, not
build queues. Before building from them, refactor the item into current
project state: re-check relevant `PLAN.md` modules, `STATUS.md`,
`ideas/PIPELINE.md`, recent commits, active review gates, prior-provider
memories, related implication lanes, and the provider-context feed for the
current phase; then add/update a STATUS row with exact Files, Depends, branch,
worktree, PR expectation, PLAN module refs, memory refs, and related
implication refs. If there are relevant `ideas/INBOX.md` captures, park them
at the bottom of the lane as Idea feed refs.

## The Save Point Pattern

```
Agent starts work
    │
    ├── Makes a change
    │   ├── Test passes? → Commit → Continue
    │   └── Test fails? → Revert to last commit → Investigate
    │
    ├── Makes another change
    │   ├── Test passes? → Commit → Continue
    │   └── Test fails? → Revert to last commit → Investigate
    │
    └── Feature complete → All commits form a clean history
```

This pattern means you never lose more than one increment of work. If an agent goes off the rails, `git reset --hard HEAD` takes you back to the last successful state.

## Change Summaries

After any modification, provide a structured summary. This makes review easier, documents scope discipline, and surfaces unintended changes:

```
CHANGES MADE:
- src/routes/tasks.ts: Added validation middleware to POST endpoint
- src/lib/validation.ts: Added TaskCreateSchema using Zod

THINGS I DIDN'T TOUCH (intentionally):
- src/routes/auth.ts: Has similar validation gap but out of scope
- src/middleware/error.ts: Error format could be improved (separate task)

POTENTIAL CONCERNS:
- The Zod schema is strict — rejects extra fields. Confirm this is desired.
- Added zod as a dependency (72KB gzipped) — already in package.json
```

This pattern catches wrong assumptions early and gives reviewers a clear map of the change. The "DIDN'T TOUCH" section is especially important — it shows you exercised scope discipline and didn't go on an unsolicited renovation.

## Pre-Commit Hygiene

Before every commit:

```bash
# 1. Check what you're about to commit
git diff --staged

# 2. Ensure no secrets
git diff --staged | grep -i "password\|secret\|api_key\|token"

# 3. Run tests
npm test

# 4. Run linting
npm run lint

# 5. Run type checking
npx tsc --noEmit
```

Automate this with git hooks:

```json
// package.json (using lint-staged + husky)
{
  "lint-staged": {
    "*.{ts,tsx}": ["eslint --fix", "prettier --write"],
    "*.{json,md}": ["prettier --write"]
  }
}
```

## Handling Generated Files

- **Commit generated files** only if the project expects them (e.g., `package-lock.json`, Prisma migrations)
- **Don't commit** build output (`dist/`, `.next/`), environment files (`.env`), or IDE config (`.vscode/settings.json` unless shared)
- **Have a `.gitignore`** that covers: `node_modules/`, `dist/`, `.env`, `.env.local`, `*.pem`

## Using Git for Debugging

```bash
# Find which commit introduced a bug
git bisect start
git bisect bad HEAD
git bisect good <known-good-commit>
# Git checkouts midpoints; run your test at each to narrow down

# View what changed recently
git log --oneline -20
git diff HEAD~5..HEAD -- src/

# Find who last changed a specific line
git blame src/services/task.ts

# Search commit messages for a keyword
git log --grep="validation" --oneline
```

## Common Rationalizations

| Rationalization | Reality |
|---|---|
| "I'll commit when the feature is done" | One giant commit is impossible to review, debug, or revert. Commit each slice. |
| "The message doesn't matter" | Messages are documentation. Future you (and future agents) will need to understand what changed and why. |
| "I'll squash it all later" | Squashing destroys the development narrative. Prefer clean incremental commits from the start. |
| "Branches add overhead" | Short-lived branches are free and prevent conflicting work from colliding. Long-lived branches are the problem — merge within 1-3 days. |
| "I'll split this change later" | Large changes are harder to review, riskier to deploy, and harder to revert. Split before submitting, not after. |
| "I don't need a .gitignore" | Until `.env` with production secrets gets committed. Set it up immediately. |

## Red Flags

- Large uncommitted changes accumulating
- Commit messages like "fix", "update", "misc"
- Formatting changes mixed with behavior changes
- No `.gitignore` in the project
- Committing `node_modules/`, `.env`, or build artifacts
- Long-lived branches that diverge significantly from main
- Force-pushing to shared branches

## Verification

For every commit:

- [ ] Commit does one logical thing
- [ ] Message explains the why, follows type conventions
- [ ] Tests pass before committing
- [ ] No secrets in the diff
- [ ] No formatting-only changes mixed with behavior changes
- [ ] `.gitignore` covers standard exclusions
