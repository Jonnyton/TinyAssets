---
name: planning-and-task-breakdown
description: Breaks work into ordered, bite-sized tasks and executes them. Use when you have a spec or clear requirements, when a task feels too large or vague to start, when work can be parallelized, or when you have a written plan to execute.
---

# Planning and Task Breakdown

## Overview

Decompose work into small, independently verifiable tasks with explicit
acceptance criteria, then execute them one at a time with checkpoints. Good
breakdown is the difference between reliable completion and a tangled mess.
Planning *is* the task — implementation without a plan is just typing.

## When to Use

You have a spec to turn into tasks · a task feels too large/vague · work spans
multiple sessions or agents · you have a written plan to execute. **Skip for**
single-file changes with obvious scope.

---

## Part 1 — Writing the plan

### Plan first (read-only)

Before writing code, read the spec and relevant code, identify existing patterns
and conventions, map dependencies, note risks and unknowns. The output is a plan
document, not implementation.

### Map the dependency graph and slice vertically

Order follows the dependency graph bottom-up (schema → models → endpoints →
client → UI). But slice work **vertically** — one complete feature path at a
time ("user can register" = schema+API+UI) rather than horizontally ("all
schema, then all API"). Each vertical slice delivers working, testable
functionality.

### Decide file structure

Map which files each task creates/modifies and what each is responsible for —
one clear responsibility per file, files that change together live together
(split by responsibility, not technical layer). Prefer smaller focused files. In
existing codebases, follow established patterns; don't unilaterally restructure.

### Right-size tasks, write bite-sized steps

A **task** is the smallest unit that carries its own test cycle and is worth a
fresh reviewer's gate — it ends with an independently testable deliverable. Fold
setup/config/scaffolding/docs into the task whose deliverable needs them; split
only where a reviewer could reject one task while approving its neighbor.

Within a task, each **step** is one 2–5 minute action:
write the failing test → run it, watch it fail → write minimal code → run it,
watch it pass → commit.

| Size | Files | Break down if… |
|------|-------|----------------|
| XS–S | 1–2 | — |
| M | 3–5 | sweet spot for an agent |
| L | 5–8 | borderline — prefer splitting |
| XL | 8+ | **too large, always break down** |

Break a task down further when it needs >1 focused session, can't be described
in ≤3 acceptance bullets, touches 2+ independent subsystems, or has "and" in its
title.

### Task structure

```markdown
### Task N: [Component]
**Files:** Create/Modify (exact paths + line ranges) / Test
**Interfaces:** Consumes (signatures from earlier tasks) · Produces (exact
  names/types later tasks rely on — the implementer sees only their own task)
**Precedent research:** required | optional | skip
**Research question:** <exact implementation decision; omit when skipped>
- [ ] Step 1: write failing test (actual test code)
- [ ] Step 2: run it, expect FAIL with <reason>
- [ ] Step 3: minimal implementation (actual code)
- [ ] Step 4: run it, expect PASS
- [ ] Step 5: commit
**Acceptance:** specific, testable conditions
**Verification:** exact commands + expected output
```

Choose the precedent field after checking requirements, edit targets, tests,
and a likely internal precedent. `required` means dispatch
`implementation-precedent-scout` before coding; `optional` lets the implementer
dispatch only after naming unresolved implementation uncertainty; `skip` covers
mechanical or canonical-pattern work. The field does not authorize strategic
design research or expand the task.

### No placeholders

Every step contains the actual content needed. These are plan failures: "TBD /
TODO / implement later", "add appropriate error handling", "write tests for the
above" (without the test code), "similar to Task N" (repeat the code — tasks may
be read out of order), references to types/functions not defined in any task.

### Self-review before handoff

With fresh eyes against the spec: (1) **coverage** — every requirement maps to a
task; (2) **placeholder scan** — fix any; (3) **type consistency** — names and
signatures used in later tasks match earlier definitions. Fix inline.

---

## Part 2 — Executing the plan

1. **Load and review critically.** Raise concerns before starting. Create todos
   from the plan items.
2. **Execute task-by-task.** Mark in-progress, follow each step exactly, run the
   specified verifications, mark complete. Don't skip verifications.
3. **Checkpoint every 2–3 tasks** — tests pass, build clean, core flow works
   end-to-end, review before proceeding. Keep the system in a working state
   after every task; do high-risk tasks early (fail fast).
4. **Stop and ask, don't guess,** on any blocker: missing dependency, repeated
   verification failure, unclear instruction, critical plan gap. Never start
   implementation on main/master without explicit consent.

Where subagents are available, dispatch a fresh one per task with review between
tasks (`subagent-driven-development`) for higher quality; otherwise execute
inline in batches. Isolate the work in a worktree (`git-workflow-and-versioning`)
and complete via the finish/merge flow in that same skill.

## Parallelization

Safe to parallelize: independent feature slices, tests for already-built
features, docs. Sequential only: migrations, shared-state changes, dependency
chains. Needs coordination: features sharing an API contract — define the
contract first, then parallelize.

## Red Flags

Starting implementation with no written task list · tasks without acceptance
criteria or verification · all tasks XL-sized · no checkpoints · dependency order
ignored · forcing through a blocker instead of asking.

## Verification

- [ ] Every task has acceptance criteria and a verification step
- [ ] No task touches more than ~5 files; steps are bite-sized
- [ ] Dependencies ordered correctly; checkpoints between phases
- [ ] No placeholders; types consistent across tasks
- [ ] Human reviewed/approved the plan before execution
