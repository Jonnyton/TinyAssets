---
name: using-agent-skills
description: Discovers and invokes agent skills. Use when starting a session or when you need to decide which skill or sequence of skills fits the current task.
---

# Using Agent Skills

## Overview

Agent skills are workflow modules. This meta-skill is the router: pick the
right specialist skill, then follow that skill's process instead of trying to
do everything from memory.

Keep this file thin. Do not stuff specialist guidance into the router when a
dedicated skill should own it.

## Discovery

When a task arrives, identify the dominant need first:

```text
Task arrives
    |
    |-- Unfamiliar area / need bigger map? ----------> zoom-out
    |-- Need to create or update a skill? -----------> skill-authoring
    |-- Vague idea / need refinement? ---------------> idea-refine
    |-- Domain terms drifting / overloaded? ---------> ubiquitous-language
    |-- Need to challenge plan vs domain model? -----> domain-model
    |-- Old/classic game design or proof? -----------> classic-game-design-test
    |-- Architecture or modularity audit? -----------> improve-codebase-architecture
    |-- New feature / change with no spec? ----------> spec-driven-development
    |-- Have a spec, need tasks? --------------------> planning-and-task-breakdown
    |-- Implementing code? --------------------------> incremental-implementation
    |   |-- Website edit / preview loop? -----------> website-editing
    |   |-- Game or interactive prototype? ---------> game-prototyping
    |   |-- UI work? --------------------------------> frontend-ui-engineering
    |   |-- API / interface work? -------------------> api-and-interface-design
    |   |-- Mostly simplification / clarity? --------> code-simplification
    |   `-- Need better context loaded? -------------> context-engineering
    |-- Writing or running tests? -------------------> test-driven-development
    |   |-- Conditional-edge branch routing? --------> conditional-edge-testing
    |   |-- Browser runtime verification? -----------> browser-testing-with-devtools
    |   `-- Live Claude.ai phone-surface test? ------> ui-test
    |-- Community loop unable to self-heal? ---------> loop-uptime-maintenance
    |-- Something broke? ----------------------------> debugging-and-error-recovery
    |-- Reviewing code? -----------------------------> code-review-and-quality
    |   |-- Security-sensitive? ---------------------> security-and-hardening
    |   `-- Performance-sensitive? ------------------> performance-optimization
    |-- Removing legacy systems or aliases? ---------> deprecation-and-migration
    |-- CI/CD pipeline or automation work? ----------> ci-cd-and-automation
    |-- Committing / branching / release hygiene? ---> git-workflow-and-versioning
    |-- Cloudflare dashboard or tunnel ops? ---------> cloudflare-ops
    |-- GoDaddy domain / DNS / site ops? ------------> godaddy-ops
    |-- Writing docs or rationale? ------------------> documentation-and-adrs
    |-- Deploying or launching? ---------------------> shipping-and-launch
    |-- Recurring agent behavior failed again? ------> auto-iterate
    `-- Agent-team behavior needs tuning? -----------> team-iterate
```

## Rules

1. Check for an applicable skill before starting substantive work.
2. Use the minimum set of skills that covers the task.
3. Let specialist skills own specialist instructions.
4. When two skills overlap, route by the primary job:
   - `using-agent-skills` chooses.
   - `skill-authoring` writes or updates skills.
   - `domain-model` stress-tests concepts and boundaries.
   - `ubiquitous-language` hardens terminology.
   - `improve-codebase-architecture` audits seams and modularity.
5. Multiple skills can be chained. Example:
   `zoom-out -> improve-codebase-architecture -> planning-and-task-breakdown -> incremental-implementation -> test-driven-development`.

## Core Behaviors

These apply across all skills:

### 1. Surface assumptions

State non-trivial assumptions before acting on them.

```text
ASSUMPTIONS:
1. ...
2. ...
3. ...
```

### 2. Manage confusion actively

If the spec, code, tests, or docs disagree:

1. Stop.
2. Name the contradiction.
3. Prefer an autonomous default when it is reversible and low-risk.
4. Record unresolved risk in `STATUS.md` or the relevant spec when it matters.
5. Ask the user only when no safe default exists.

### 3. Push back when warranted

Say why an approach is weak, quantify the downside when possible, and propose
the smaller or safer alternative.

### 4. Enforce simplicity

Prefer boring, legible solutions over clever ones. If a dedicated skill exists
for the work, use it instead of inventing a one-off process.

### 5. Maintain scope discipline

Touch only what the task requires. Do not turn one request into an unrelated
cleanup campaign.

### 6. Verify, do not assume

Every task needs evidence: tests, build output, runtime checks, or document
diffs. "Looks right" is not completion.

## Lifecycle

For larger work, the common sequence is:

```text
1. using-agent-skills
2. zoom-out (if the area is unfamiliar)
3. idea-refine or spec-driven-development
4. planning-and-task-breakdown
5. context-engineering
6. incremental-implementation
7. test-driven-development
8. code-review-and-quality
9. documentation-and-adrs
10. git-workflow-and-versioning
11. shipping-and-launch
```

Not every task needs every step. Bug triage might be:
`zoom-out -> debugging-and-error-recovery -> test-driven-development -> code-review-and-quality`.

## Quick Reference

| Phase | Skill | One-line summary |
|-------|-------|------------------|
| Orient | zoom-out | Build a high-level map before diving into details |
| Define | idea-refine | Refine ideas through structured divergence and convergence |
| Define | ubiquitous-language | Harden domain terms and remove naming drift |
| Define | domain-model | Stress-test a plan against concepts, invariants, and boundaries |
| Define | classic-game-design-test | Design and prove old-game experiences without silently substituting remakes |
| Define | spec-driven-development | Write requirements and acceptance criteria before code |
| Plan | planning-and-task-breakdown | Decompose work into small verifiable tasks |
| Build | incremental-implementation | Ship thin vertical slices |
| Build | website-editing | Edit the Workflow website with its preview and ship loop |
| Build | game-prototyping | Build playable browser games and game-like interactive prototypes |
| Build | context-engineering | Load the right context at the right time |
| Build | frontend-ui-engineering | Build production-quality user interfaces |
| Build | api-and-interface-design | Design stable interfaces and contracts |
| Build | code-simplification | Simplify working code without changing behavior |
| Build | improve-codebase-architecture | Find and fix weak module boundaries |
| Verify | test-driven-development | Write failing tests first, then make them pass |
| Verify | conditional-edge-testing | Require compile+invoke coverage for conditional-edge branches |
| Verify | browser-testing-with-devtools | Use browser runtime evidence to verify behavior |
| Verify | ui-test | Exercise the live Claude.ai user surface |
| Ops | loop-uptime-maintenance | Handle community-loop failures too broken to self-heal through the loop |
| Verify | debugging-and-error-recovery | Reproduce, localize, fix, and guard regressions |
| Review | code-review-and-quality | Review by bugs, regressions, and missing tests first |
| Review | security-and-hardening | Apply least privilege and hostile-input thinking |
| Review | performance-optimization | Measure first, then optimize what matters |
| Change | deprecation-and-migration | Remove or migrate legacy systems deliberately |
| Ship | git-workflow-and-versioning | Keep branches and commits intentional |
| Ship | ci-cd-and-automation | Automate quality gates and recurring checks |
| Ship | documentation-and-adrs | Record durable design context and rationale |
| Ship | shipping-and-launch | Deploy with monitoring and rollback discipline |
| Ops | cloudflare-ops | Operate Cloudflare DNS, routes, and website surfaces |
| Ops | godaddy-ops | Operate GoDaddy domain and site surfaces |
| Meta | skill-authoring | Create or update project-local skills correctly |
| Meta | auto-iterate | Ratchet prevention after repeated agent behavioral failures |
| Meta | team-iterate | Improve agent-team definitions and launch prompts |
