---
name: using-agent-skills
description: Discovers and invokes agent skills, and establishes the discipline of using them. Use when starting a session or when you need to decide which skill or sequence of skills fits the current task.
---

# Using Agent Skills

## Overview

Agent skills are workflow modules. This meta-skill is the router: pick the right
specialist skill, then follow that skill's process instead of working from
memory. Keep this file thin — specialist guidance lives in the specialist skill.

## The discipline (invoke skills before acting)

**Invoke a skill when it would change what you do next.** Concretely, before
acting on a task, check the router below and invoke the matching skill if either
holds:

- The task is one the skill names in its `description` trigger, **and** you would
  otherwise work from memory rather than from its process; or
- The work is about to become hard to reverse — a push, a merge, a deploy, a
  schema or public-surface change — and a skill governs that gate.

Skip it when you already know the skill's answer and the step is trivially
reversible (a typo fix, a one-line comment, a lookup). Say so in one line if the
call is close, so the skip is visible rather than silent.

If an invoked skill turns out to be wrong for the situation, you don't have to
use it. User instructions in `AGENTS.md` / `CLAUDE.md` always take precedence
over a skill where they conflict.

> This replaced a "~1% chance it applies → always invoke" rule on 2026-08-07. A
> usage audit found 25 of 33 skills had never been dispatched across 332 sessions:
> the absolute form was being ignored wholesale rather than followed, which is
> worse than a narrower rule that actually gets applied.

## Discovery

Identify the dominant need first:

```text
Task arrives
    |
    |-- Unfamiliar area / need a bigger map? --------> improve-codebase-architecture
    |-- Outside repo, paper, project implications? --> external-research-implications
    |-- Vague idea / design not approved yet? -------> idea-refine
    |-- Domain terms drifting / concept integrity? --> domain-model
    |-- New feature / change with no spec? ----------> openspec
    |-- Have a spec, need tasks / executing a plan? -> planning-and-task-breakdown
    |-- Independent tasks / plan via subagents? -----> subagent-driven-development
    |-- Implementing code? --------------------------> incremental-implementation
    |   |-- TinyAssets website edit? ------------------> website-editing
    |   `-- Mostly simplification / least code? -----> code-simplification
    |-- Need better context loaded? -----------------> context-engineering
    |-- Writing or running tests? -------------------> test-driven-development
    |   |-- Browser runtime verification? -----------> browser-testing-with-devtools
    |   `-- Live Claude.ai phone-surface test? ------> ui-test
    |-- Something broke? ----------------------------> debugging-and-error-recovery
    |-- Reviewing code / verifying completion? ------> code-review-and-quality
    |   `-- Security-sensitive? ---------------------> security-and-hardening
    |-- Committing / branching / worktrees / merge? -> git-workflow-and-versioning
    |-- CI gates / deploy / launch / rollout? -------> shipping-and-launch
    |-- Cloudflare / GoDaddy / DNS / domain ops? ----> infra-ops
    |-- Writing docs or rationale? ------------------> documentation-and-adrs
    |-- Create/update a skill? ----------------------> skill-authoring
    `-- Recurring agent failure / tune the team? ----> auto-iterate
```

## Rules

1. Check for an applicable skill before starting substantive work.
2. Use the minimum set of skills that covers the task.
3. Let specialist skills own specialist instructions; keep this router thin.
4. Multiple skills chain. Example:
   `improve-codebase-architecture -> planning-and-task-breakdown ->
   incremental-implementation -> test-driven-development -> code-review-and-quality`.

## Core Behaviors (apply across all skills)

1. **Surface assumptions** before acting on them.
2. **Manage confusion actively** — if spec/code/tests/docs disagree, stop, name
   the contradiction, prefer a reversible default, ask only when no safe default
   exists.
3. **Push back when warranted** — quantify the downside, propose the smaller/safer
   alternative.
4. **Enforce simplicity** — prefer boring, legible solutions; use the dedicated
   skill instead of inventing a one-off process.
5. **Maintain scope discipline** — touch only what the task requires.
6. **Verify, don't assume** — evidence (tests, build output, runtime checks, diffs)
   before any completion claim. "Looks right" is not done.

## Lifecycle

A common sequence for larger work (not every task needs every step):

```text
idea-refine -> openspec -> planning-and-task-breakdown
-> context-engineering -> incremental-implementation -> test-driven-development
-> code-review-and-quality -> documentation-and-adrs -> git-workflow-and-versioning
-> shipping-and-launch
```

Bug triage might be: `debugging-and-error-recovery -> test-driven-development ->
code-review-and-quality`.

## Quick Reference

| Phase | Skill | One-line summary |
|-------|-------|------------------|
| Orient | improve-codebase-architecture | Map an area, then audit module boundaries and coupling |
| Orient | external-research-implications | Turn outside repos/papers into TinyAssets implications |
| Orient | peer-agents | Dispatch work to the Claude or Codex CLI on that subscription's budget |
| Define | idea-refine | Refine an idea into an approved design before building |
| Define | domain-model | Stress-test concepts/invariants and harden terminology |
| Define | openspec | CLI-managed multi-session spec lifecycle |
| Plan | planning-and-task-breakdown | Decompose into bite-sized tasks and execute them |
| Plan | subagent-driven-development | Execute via fresh subagents; parallel-dispatch independent work |
| Build | incremental-implementation | Ship thin vertical slices |
| Build | context-engineering | Load the right context at the right time |
| Build | website-editing | TinyAssets site preview / capture / ship conventions |
| Build | code-simplification | Write the least code that works; simplify existing code |
| Verify | test-driven-development | Write failing tests first, then make them pass |
| Verify | browser-testing-with-devtools | Verify behavior with real browser runtime evidence |
| Verify | ui-test | Exercise the live Claude.ai user surface |
| Verify | debugging-and-error-recovery | Reproduce, find root cause, fix, guard regressions |
| Review | code-review-and-quality | Conduct/request/receive review; gate completion on evidence |
| Review | security-and-hardening | Least privilege and hostile-input thinking |
| Ship | git-workflow-and-versioning | Commits, branches, worktrees, branch completion |
| Ship | shipping-and-launch | CI gates, staged rollout, monitoring, rollback |
| Ship | documentation-and-adrs | Record durable design context and rationale |
| Ops | infra-ops | Cloudflare/GoDaddy DNS, domains, Workers, SSL |
| Meta | skill-authoring | Create/update project skills correctly |
| Meta | auto-iterate | Ratchet recurring failures into guards; tune the agent team |
