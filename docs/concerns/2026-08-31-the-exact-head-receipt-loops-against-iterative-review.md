# The exact-head receipt and the three-round cap pull against each other

**Filed:** 2026-08-31
**Verified:** 2026-08-31, PR #2755 (`claude/labeled-credential-fields`), four review
passes across heads `070ead76` -> `fcc1ca64` -> `520ba707` -> `255391be`.
**Severity:** P2 — process, not product. It costs review budget and it pushes
toward exactly the behaviour both rules exist to prevent.

## The bind

Two rules that are each right on their own:

* `pr-scope-guard` requires a `Drain-Review-Verdict/Head/Artifact` receipt on any
  PR touching an authority path, **voided by any push** — so the receipt has to
  name the head that ships. That is the point: a receipt for a tree nobody ships
  is not evidence.
* `AGENTS.md` caps review at **three rounds, then escalate**, on published
  evidence that defect counts across rounds are non-monotonic and that fixing
  round N's findings often creates round N+1's.

Put together on a PR whose reviews keep finding real defects, they have no exit.
Every fix voids the receipt; every new receipt needs another pass; the cap says
the passes must stop. The only terminating states are **a pass that finds
nothing**, or **a human decision**.

## What it looked like here

Findings per pass: **7 -> 5 -> 1 -> 3**. Non-monotonic, as predicted. The fourth
pass found a weakness in a test written during the third — the specific failure
mode `AGENTS.md` cites from PR #2561.

All three findings in the fourth pass were real, and two were **pre-existing**
bugs that the change merely made reachable. So "the reviews are still finding
things" and "the reviews are in the documented churn mode" were both true at
once, which is what makes the call hard rather than obvious.

## Why it is not simply "stop reviewing"

The pressure this creates is toward the wrong resolution. Facing an unbounded
loop, the tempting moves are to stop fixing real findings so the receipt sticks,
or to stamp a receipt for a head that was never reviewed. The first ships known
defects; the second makes the gate decorative — and a gate that is routinely
worked around is worse than none, because it still reads as evidence.

## What would actually fix it

Not obvious, and deliberately not decided here:

* **A receipt that covers a RANGE**, valid while later commits are confined to
  what the review asked for. Needs a way to tell "fixed your finding" from "and
  also rewrote the gate", which is the thing the exact-head rule buys cheaply.
* **A receipt-only final pass** whose declared scope is "does the fix to the
  previous finding hold", explicitly not a new hunt — which is what was done
  here for `520ba707`, and it still returned three findings, so the scoping did
  not bound it.
* **A founder decision as a first-class terminator**, recorded like a receipt.
  Today the escalation has nowhere to land: `AGENTS.md` says take it to the
  founder, and CI has no way to represent "the founder looked at this".

The third is the smallest and probably the honest one — the cap already assumes
a human ends the loop, and the gate has no representation for that.

## Related

* `docs/reference/executable-gates.md` — enforced vs judgement.
* `.github/workflows/pr-scope-guard.yml` — `AUTHORITY_RE`, `--require-receipt`.
* `AGENTS.md` — Quality Gates, "Three rounds, then escalate".
