## 1. Regression contracts

- [x] 1.1 Add a prompt regression proving refinery workers distinguish the exact next slice's immediate prerequisites from downstream completion evidence and must search autonomous prerequisite-removal work before `BLOCKED`; observe RED.
- [x] 1.2 Add a continuation regression proving a merged refinery `PARTIAL` is rejected when fresh current main exposes no claimable row in the assigned change boundary; observe RED.
- [x] 1.3 Add a watchdog regression proving an explicit restart of a live supervisor that exits through orderly `stop-requested` resumes the same run directory and drain identity; observe RED.

## 2. Implementation

- [x] 2.1 Tighten the refinery brief to produce an immediately executable slice or the shortest concrete autonomous prerequisite-removal slice without weakening claim/collision/host gates.
- [x] 2.2 Validate verified refinery continuations against fresh current-main claimability and record a bounded invalid-continuation result when coordination did not open delivery capacity.
- [x] 2.3 Add the cross-provider row-semantics rule to `AGENTS.md` and record the 24-attempt/zero-slice incident evidence.
- [x] 2.4 Preserve the active run directory and identity when an explicit watchdog restart ends through orderly `stop-requested`; retain fresh-run recovery for already-terminal fatal/failure-budget state. Completed test-first 2026-08-01: the new orderly-stop regression failed because restart created a new directory, then passed alongside the existing terminal-failure fresh-run regression after the watchdog distinguished those outcomes.

## 3. Verification and foldback

- [x] 3.1 Run focused controller tests, lint/format, strict OpenSpec validation, and independent exact-head review. Completed 2026-08-01 on Windows at exact implementation head `0b35c99b`: 191 focused tests passed, Ruff and strict OpenSpec were clean, and opposite-provider Claude review returned `APPROVE`.
- [ ] 3.2 Re-run focused tests/lint/strict OpenSpec and exact-head review, land through a reviewed PR, restore the original `drain-20260801-113628-6deab6` run, prove its existing claim resumes automatically, then sync/archive and retire the STATUS row. Earlier admission proof remains valid: attempt 33 merged #2103, and attempt 34 admitted and merged the bounded owner-gate slice as #2106 before the restart identity regression surfaced.
