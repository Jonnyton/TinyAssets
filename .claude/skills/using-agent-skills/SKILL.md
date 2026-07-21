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

If there is even a ~1% chance a skill applies to what you're doing, invoke it
before responding or acting — including before asking clarifying questions. If an
invoked skill turns out to be wrong for the situation, you don't have to use it.
User instructions in `AGENTS.md` / `CLAUDE.md` always take precedence over a
skill where they conflict.

## Discovery

Identify the dominant need first:

```text
Task arrives
    |
    |-- Unfamiliar area / need a bigger map? --------> improve-codebase-architecture
    |-- Outside repo, paper, project implications? --> external-research-implications
    |-- Vague idea / design not approved yet? -------> idea-refine
    |-- Domain terms drifting / concept integrity? --> domain-model
    |-- New feature / change with no spec? ----------> spec-driven-development
    |   `-- Using the OpenSpec CLI for it? ----------> openspec
    |-- Have a spec, need tasks / executing a plan? -> planning-and-task-breakdown
    |-- Independent tasks / plan via subagents? -----> subagent-driven-development
    |-- Implementing code? --------------------------> incremental-implementation
    |   |-- UI work? --------------------------------> frontend-ui-engineering
    |   |-- Game or interactive prototype? ----------> game-prototyping
    |   |-- Restore/emulate/prove an OLD game? ------> classic-game-design-test
    |   |-- TinyAssets website edit? ------------------> website-editing
    |   |-- API / interface work? -------------------> api-and-interface-design
    |   `-- Mostly simplification / least code? -----> code-simplification
    |-- Need better context loaded? -----------------> context-engineering
    |-- Writing or running tests? -------------------> test-driven-development
    |   |-- Conditional-edge branch routing? --------> conditional-edge-testing
    |   |-- Browser runtime verification? -----------> browser-testing-with-devtools
    |   `-- Live Claude.ai phone-surface test? ------> ui-test
    |-- Something broke? ----------------------------> debugging-and-error-recovery
    |-- Reviewing code / verifying completion? ------> code-review-and-quality
    |   |-- Security-sensitive? ---------------------> security-and-hardening
    |   `-- Performance-sensitive? ------------------> performance-optimization
    |-- Removing legacy systems or aliases? ---------> deprecation-and-migration
    |-- Committing / branching / worktrees / merge? -> git-workflow-and-versioning
    |-- CI gates / deploy / launch / rollout? -------> shipping-and-launch
    |-- Cloudflare / GoDaddy / DNS / domain ops? ----> infra-ops
    |-- Loop cannot self-heal its own break? --------> loop-uptime-maintenance
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
idea-refine -> spec-driven-development (or openspec) -> planning-and-task-breakdown
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
| Define | spec-driven-development | Write requirements and acceptance criteria before code |
| Define | openspec | CLI-managed multi-session spec lifecycle |
| Plan | planning-and-task-breakdown | Decompose into bite-sized tasks and execute them |
| Plan | subagent-driven-development | Execute via fresh subagents; parallel-dispatch independent work |
| Build | incremental-implementation | Ship thin vertical slices |
| Build | context-engineering | Load the right context at the right time |
| Build | frontend-ui-engineering | Build production-quality UIs |
| Build | game-prototyping | Build playable game-like prototypes |
| Build | classic-game-design-test | Restore/emulate/port/prove playability of old games |
| Build | website-editing | TinyAssets site preview / capture / ship conventions |
| Build | api-and-interface-design | Design stable interfaces and contracts |
| Build | code-simplification | Write the least code that works; simplify existing code |
| Verify | test-driven-development | Write failing tests first, then make them pass |
| Verify | conditional-edge-testing | Compile+invoke coverage for conditional-edge branches |
| Verify | browser-testing-with-devtools | Verify behavior with real browser runtime evidence |
| Verify | ui-test | Exercise the live Claude.ai user surface |
| Verify | debugging-and-error-recovery | Reproduce, find root cause, fix, guard regressions |
| Review | code-review-and-quality | Conduct/request/receive review; gate completion on evidence |
| Review | security-and-hardening | Least privilege and hostile-input thinking |
| Review | performance-optimization | Measure first, then optimize what matters |
| Change | deprecation-and-migration | Remove or migrate legacy systems deliberately |
| Ship | git-workflow-and-versioning | Commits, branches, worktrees, branch completion |
| Ship | shipping-and-launch | CI gates, staged rollout, monitoring, rollback |
| Ship | documentation-and-adrs | Record durable design context and rationale |
| Ops | infra-ops | Cloudflare/GoDaddy DNS, domains, Workers, SSL |
| Ops | loop-uptime-maintenance | Handle loop outages that can't self-heal via the loop |
| Meta | skill-authoring | Create/update project skills correctly |
| Meta | auto-iterate | Ratchet recurring failures into guards; tune the agent team |
