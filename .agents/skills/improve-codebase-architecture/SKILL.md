---
name: improve-codebase-architecture
description: Maps a code area then audits module boundaries, coupling, and naming drift to improve testability and navigability. Use when entering an unfamiliar area, needing broader context before changing code, or for an architecture / spaghetti-code / modularity review.
---

# Improve Codebase Architecture

## Overview

Go up one layer before diving in, then fix the structural problems that make code
hard to reason about, test, or change. Prefer boundary fixes and clearer
ownership over large rewrites.

## 1. Orient on live truth

- Read `STATUS.md` first.
- **Read the relevant `## Module:` section in `PLAN.md`** before auditing any code
  in that module's footprint. PLAN.md is the working theory of what each module
  owns; the audit measures actual code against it.
- If a documented principle conflicts with the current code, surface the
  contradiction before proposing changes — that contradiction is the audit's
  primary finding.

### 1a. Run the stale-audit check

Before claiming any module is fine, run `python scripts/plan_module_audit.py`. It
lists `_Last audited: YYYY-MM-DD_` stamps per module plus substrate paths that no
longer exist on disk (drift). A module's last audit is the prior anchor; this
audit confirms the prior shape or records what changed.

## 2. Build the map (zoom out)

Get a fast, usable map before detail work:

- **Trace inward** — main entrypoints and callers: commands, endpoints, UI flows,
  scheduled jobs, tests that exercise the area.
- **Trace outward** — dependencies and side effects: storage, external services,
  subprocesses, background jobs, config/environment.
- **Mark boundaries** — handoff points between modules, where policy lives, where
  orchestration lives, where I/O begins; note key invariants.

If you only needed orientation, stop here with a compact map (mission, main
modules, inbound callers, outbound deps, invariants) and route to the next skill:
`debugging-and-error-recovery` for failures, `test-driven-development` for
behavior work, `domain-model` for
concept/terminology problems, or continue below for seam problems. Don't call a
module "spaghetti" until you can name the missing seam.

## 3. Look for architectural smells

God modules mixing orchestration/policy/I/O · cross-layer imports bypassing
boundaries · duplicated orchestration spread across files · hidden global state or
ambient config · naming drift hiding distinct concepts behind one term · shallow
wrappers with no abstraction value · modules hard to test because pure logic and
side effects are fused.

## 4. Judge by change cost

Report the issues that most damage testability, local reasoning, onboarding/AI
navigability, and safe incremental change. Small, high-leverage seam fixes beat
ambitious rewrites.

## 5. Recommend boundary-first changes

Prefer: extract pure policy from I/O wrappers · split orchestration from leaf
operations · explicit interfaces at subsystem edges · rename overloaded concepts ·
collapse accidental indirection. Avoid: repo-wide churn without proof, stylistic
refactors disguised as architecture, broad renames without a canonical-language
decision (`domain-model`).

## 6. Deliver findings in severity order

For each: the behavior/maintenance problem it causes, where the seam breaks, the
smallest credible fix, and what should stay unchanged for now. Use file
references and concrete failure modes, not vague "clean architecture" talk. If you
implement a fix, keep the diff surgical and prove behavior is unchanged except
where intended.

## After the audit — stamp + ratchet

1. **Update the `_Last audited:` stamp** in the module's `PLAN.md` section to
   today — the visible signal for the next session that the module was reviewed.
2. **Check for recurrence.** If a smell found here was also found in the
   *previous* audit of the same module (per PLAN.md git history or the audit
   trail), invoke `auto-iterate` — two consecutive audits with the same finding
   means ratchet the prevention layer (doc → script → hook → gate).

## Verification

- [ ] Read the module's PLAN.md section; ran `plan_module_audit.py`
- [ ] The map includes both callers and dependencies; boundaries named
- [ ] Findings map to named module boundaries, not vibes; changes incremental and testable
- [ ] PLAN.md module section + `_Last audited:` stamp updated; `STATUS.md` updated when a contradiction matters
- [ ] No unrelated cleanup leaked into the implementation
