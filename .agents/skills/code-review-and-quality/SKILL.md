---
name: code-review-and-quality
description: Conducts, requests, and responds to code review, and gates completion claims on evidence. Use when merging any change, when evaluating code from yourself/another agent/a human, when receiving review feedback, or before claiming work is done.
---

# Code Review and Quality

## Overview

Every change gets reviewed before merge — no exceptions. This skill covers the
full loop: conducting a review, requesting one, responding to feedback, and the
non-negotiable verification gate before any "done" claim.

**Approval standard:** approve when a change *definitely improves overall code
health*, even if imperfect. Don't block because it isn't how you'd have written
it. Perfect code doesn't exist; the goal is continuous improvement.

## Review sequencing — shape before hardening (founder directive 2026-08-20)

Reviews run in order, and the order is load-bearing:

1. **Pre-first-build / first-draft review = SHAPE + APPROACH.** One pass, not a
   gauntlet — right architecture, fail-closed vs fail-open, one general primitive
   vs per-channel spaghetti, the right authority/ownership model, plus any
   basic-safety hole that leaks/exfils/bypasses even for a single user.
2. **Ship LIVE as MVP** (flip the dark flags on, deploy) and **test as a real
   user** through Slack / the app / the chatbot connector — the live user path is
   the shape oracle; only it proves the shape + UX flow are right.
3. **THEN the deep security-hardening rounds** — concurrency, TOCTOU,
   durability/crash, timing side-channels, migrations of hypothetical prior
   state, abuse-at-scale — AFTER live-MVP user testing.

Do NOT gate a first-draft MVP behind multiple hardening rounds; that hardens a
shape live testing may change. Split: a hole that leaks/exfils/bypasses for ONE
founder = fix pre-live; an edge that only bites multi-tenant / concurrent / crash
= defer to post-live, tracked in the change's `REVIEW.md`. A reject→reject trend
narrowing onto ever-deeper edges on a dark, un-shipped path is the signal to
SHIP, not to review again. (AGENTS.md § Review sequencing.)

---

## Verification before completion (the gate)

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

Claiming work is done without verifying is dishonesty, not efficiency. Before any
success/completion claim or expression of satisfaction ("Done!", "Perfect!"):
identify the command that proves the claim, run it fresh and complete, read the
full output and exit code, and only then state the claim *with* the evidence.

| Claim | Requires | Not sufficient |
|-------|----------|----------------|
| Tests pass | Test output: 0 failures | Previous run, "should pass" |
| Build succeeds | Build exit 0 | Linter passed |
| Bug fixed | Original symptom test passes | Code changed, assumed fixed |
| Regression test works | Red→green verified (revert fix → must fail) | Passes once |
| Agent completed | VCS diff shows the changes | Agent reports "success" |

"Should work", "I'm confident", "just this once", "I'm tired" are not evidence.
Run the command, read the output, then claim.

---

## Conducting a review

### Five axes

1. **Correctness** — matches spec; edge cases (null/empty/boundary) and error
   paths handled; tests actually test the right thing; no off-by-one / races /
   state bugs.
2. **Readability & simplicity** — clear, consistent names (no bare
   `temp`/`data`/`result`); straightforward control flow; could it be far fewer
   lines? are abstractions earning their complexity (don't generalize before the
   third use)? any dead code / no-op shims?
3. **Architecture** — fits existing patterns; clean module boundaries; no
   needless duplication or circular dependencies; appropriate abstraction level.
4. **Security** — input validated at boundaries; no secrets in code/logs;
   authz/authn where needed; parameterized queries; external data treated as
   untrusted. Deep guidance: `security-and-hardening`.
5. **Performance** — no N+1, unbounded loops/fetches, missing pagination, or
   heavy work in hot paths. Deep guidance: `performance-optimization`.

### Severity labels (required on every comment)

`Critical:` blocks merge (security, data loss, broken function) · *(no prefix)*
required before merge · `Nit:` optional style · `Optional:`/`Consider:`
suggestion · `FYI` informational. Unlabeled feedback makes everything look
mandatory.

### Change sizing

~100 lines = good, ~300 = acceptable if one logical change, ~1000 = split it.
Separate refactoring from feature work (two changes). Split by stacking, file
group, horizontal (shared first), or vertical slices. Large auto-refactors and
full deletions are OK when the reviewer only verifies intent.

### Dead-code hygiene & dependency discipline

After refactors, list orphaned code explicitly and **ask before deleting**.
Before adding any dependency: does the existing stack solve it? size, maintenance,
`npm audit`, license? Prefer stdlib/existing utilities — every dependency is a
liability.

### AI-generated code — extra scrutiny

Most code here is agent-written, so review for the failure modes *generation*
introduces, not just human ones (SDLC whitepaper, the "80% problem"):

- **Hallucinated / slopsquatted dependencies.** Every imported package must be
  real and the *intended* one — AI invents plausible names and attackers squat
  them. Verify each new import resolves to a known, existing package, not a
  typo-neighbor. (`check imports for real packages`.)
- **"Looks right, passes basic tests, still wrong."** The dangerous class is now
  conceptual, not syntactic: wrong business-logic assumptions, missing edge
  cases, unstated requirements. Check the change against *intent*, not just green
  tests.
- **Skipped-verification trajectory.** Fluent output that quietly skipped a check
  is worse than a visible error — confirm the claimed evidence is real (ties to
  the gate above). A second model (`mcp__codex__codex`) is a cheap way to catch
  what the author's blind spots miss.
- **Be skeptical of anything that looks clever.** Code the team can't explain is
  debugging debt it can't afford.

### Honesty

Don't rubber-stamp ("LGTM" without review), don't soften real issues, quantify
when possible ("~50ms per item", not "could be slow"), push back on flawed
approaches, and accept a well-reasoned override gracefully. Comment on code, not
people.

---

## Over-engineering pass (optional, focused)

A complexity-only sweep of a diff — one line per finding, goal is a *shorter*
diff. Tags: `delete:` (dead/speculative), `stdlib:` (hand-rolled what the
stdlib ships — name it), `native:` (dep doing what the platform does), `yagni:`
(abstraction with one impl, config nobody sets), `shrink:` (same logic, fewer
lines — show it). End with `net: -N lines possible` or `Lean already. Ship.`
Correctness/security/performance are out of scope for this pass — route those to
a normal review. Never flag a single smoke test / `assert` self-check as bloat.

---

## Requesting a review (subagent)

Dispatch a reviewer subagent with precisely-crafted context — never your session
history — so it focuses on the work product and preserves your context. Get
`BASE_SHA`/`HEAD_SHA`, dispatch a `general-purpose` subagent with the
[code-reviewer.md](code-reviewer.md) template (description, requirements, SHAs).
Review early and often: after each task in subagent-driven development, after a
major feature, before merge. Different models have different blind spots — a
second model catches what the author's misses.

---

## Receiving review feedback

Evaluate technically; don't perform. **Verify before implementing, ask before
assuming.**

- **Read fully → restate the requirement in your own words → verify against the
  actual codebase → evaluate if it's right *for this codebase* → respond.**
- **No performative agreement.** Never "You're absolutely right!", "Great
  point!", or "Thanks for catching that!" Just state the fix ("Fixed — changed X
  in Y") or push back with technical reasoning. Actions over words.
- **Unclear feedback → STOP, clarify all items first.** Items may be related;
  partial understanding yields wrong implementation.
- **Push back** when a suggestion breaks functionality, the reviewer lacks
  context, it violates YAGNI (grep — is it even used?), it's wrong for this
  stack, or it conflicts with prior architectural decisions. Use reasoning and
  reference working tests, not defensiveness.
- **Implement** blocking → simple → complex, testing each individually, no
  regressions. External feedback = suggestions to evaluate, not orders to follow.

---

## Red Flags

PRs merged with no review · review that only checks tests pass · "LGTM" without
evidence · large "too big to review" PRs · bug fix PRs without a regression test ·
comments without severity labels · accepting "I'll fix it later" · performative
agreement to feedback · **any completion claim without fresh verification.**

## Verification

- [ ] Reviewed across all five axes; findings severity-labeled
- [ ] All Critical issues resolved; Important resolved or deferred with reason
- [ ] Tests pass, build succeeds — confirmed by fresh command output
- [ ] Verification story documented (what changed, how verified)
