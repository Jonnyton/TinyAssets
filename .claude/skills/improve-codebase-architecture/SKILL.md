---
name: improve-codebase-architecture
description: Audits module boundaries, coupling, and naming drift to improve testability and navigability. Use when the user asks for an architecture review, spaghetti-code audit, modularity cleanup, seam extraction, or refactor targets for a large codebase.
---

# Improve Codebase Architecture

## Overview

Audit the codebase for structural problems that make it hard to reason about,
test, or change safely. Prefer boundary fixes and clearer ownership over large
rewrites.

## Workflow

### 1. Orient on live truth

- Read `STATUS.md` first.
- **Read the relevant `## Module:` section in `PLAN.md`** before auditing
  any code in that module's footprint. PLAN.md is the working theory of
  what each module owns; the audit measures actual code against it.
- If a documented principle conflicts with the current code, surface the
  contradiction before proposing changes — that contradiction is the
  audit's primary finding.

### 1a. Run the stale-audit check

Before claiming any module is fine, run:

```
python scripts/plan_module_audit.py
```

This lists `_Last audited: YYYY-MM-DD_` stamps per module plus any
substrate paths that no longer exist on disk (drift). A module's last
audit is the prior anchor; this audit either confirms the prior shape
or records what changed.

### 2. Build the map

Use `zoom-out` thinking first:

- main entrypoints
- inbound callers
- outbound dependencies
- state boundaries
- external side effects

Do not call a module "spaghetti" until you can name the seam that is missing.

### 3. Look for architectural smells

Prioritize:

- god modules that mix orchestration, policy, and I/O
- cross-layer imports that bypass intended boundaries
- duplicated orchestration logic spread across files
- hidden global state or ambient config
- naming drift that hides distinct concepts behind one term
- shallow wrappers that add noise but no abstraction value
- modules that are hard to test because pure logic and side effects are fused

### 4. Judge by change cost

Report the issues that most damage:

- testability
- local reasoning
- onboarding speed
- AI navigability
- safe incremental change

Small, high-leverage seam fixes beat ambitious rewrites.

### 5. Recommend boundary-first changes

Prefer:

- extract pure policy from I/O wrappers
- split orchestration from leaf operations
- create explicit interfaces at subsystem edges
- rename overloaded concepts
- collapse accidental indirection

Avoid:

- repo-wide churn without proof
- stylistic refactors disguised as architecture work
- broad renames without a canonical language decision

### 6. Deliver findings in severity order

For each finding, include:

- what behavior or maintenance problem it causes
- where the seam breaks down
- the smallest credible fix
- what should stay unchanged for now

If you implement a fix, keep the diff surgical and prove behavior did not
change except where intended.

## Output Shape

Start with findings, highest severity first. Use file references and concrete
failure modes, not vague talk about "clean architecture."

## After the audit — stamp + ratchet

Two final steps that close the loop with PLAN.md and the prevention
ladder:

1. **Update the `_Last audited:` stamp.** In the module's section in
   `PLAN.md`, set the date to today's audit. This is the visible signal
   for the next session that the module was just reviewed.
2. **Check for recurrence.** If a smell found in this audit was also
   found in the *previous* audit of the same module (per git history
   of PLAN.md or per audit doc trail), invoke the `auto-iterate` skill.
   Two consecutive audits with the same finding = ratchet the
   prevention layer (doc → script → hook → gate).

## Verification

- [ ] Findings map to named module boundaries, not vibes
- [ ] Recommended changes are incremental and testable
- [ ] Changed boundaries have tests or existing tests proving behavior
- [ ] PLAN.md module section reflects any architectural decisions the audit produced
- [ ] `_Last audited:` stamp updated in PLAN.md
- [ ] `STATUS.md` is updated when a contradiction matters
- [ ] No unrelated cleanup leaked into the implementation
