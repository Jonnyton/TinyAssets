## 1. Regression contracts

- [x] 1.1 Add a prompt regression proving refinery workers distinguish the exact next slice's immediate prerequisites from downstream completion evidence and must search autonomous prerequisite-removal work before `BLOCKED`; observe RED.
- [x] 1.2 Add a continuation regression proving a merged refinery `PARTIAL` is rejected when fresh current main exposes no claimable row in the assigned change boundary; observe RED.
- [x] 1.3 Add a watchdog regression proving an explicit restart of a live supervisor that exits through orderly `stop-requested` resumes the same run directory and drain identity; observe RED.
- [x] 1.4 Add a state regression proving an accepted refinery `PARTIAL` does not count as the first repeated implementation partial for the promoted target; observe RED.
- [x] 1.5 Add a resume regression proving an orderly terminal timestamp is cleared before a resumed run can be interrupted again; observe RED.
- [x] 1.6 Add a resume regression proving the cleared terminal timestamp is durable before result-recovery network work; observe RED. Failed with the old `ended_at` still on disk during the recovery hook.
- [x] 1.7 Add watchdog regressions proving unfinished identity preservation across abrupt stop, pending restart discovery, and launch failure; observe RED. All three failed by selecting a fresh run or consuming the marker before launch.
- [x] 1.8 Add receipt regressions proving verified `PARTIAL` PRs are recorded, migrated, and rejected on replay without resetting the failure budget; observe RED. All receipt/replay assertions failed before implementation.
- [x] 1.9 Add regressions proving boot discovery resumes orderly `stop-requested`, dry-run preserves restart intent, and replay logs name the actual result status; observe RED. All three assertions failed before the follow-up hardening.

## 2. Implementation

- [x] 2.1 Tighten the refinery brief to produce an immediately executable slice or the shortest concrete autonomous prerequisite-removal slice without weakening claim/collision/host gates.
- [x] 2.2 Validate verified refinery continuations against fresh current-main claimability and record a bounded invalid-continuation result when coordination did not open delivery capacity.
- [x] 2.3 Add the cross-provider row-semantics rule to `AGENTS.md` and record the 24-attempt/zero-slice incident evidence.
- [x] 2.4 Preserve the active run directory and identity when an explicit watchdog restart ends through orderly `stop-requested`; retain fresh-run recovery for already-terminal fatal/failure-budget state. Completed test-first 2026-08-01: the new orderly-stop regression failed because restart created a new directory, then passed alongside the existing terminal-failure fresh-run regression after the watchdog distinguished those outcomes.
- [x] 2.5 Reset implementation-partial stall accounting after an accepted refinery handoff while preserving repeated normal-worker partial failure-budget protection. Completed test-first 2026-08-01: the regression failed with the refinery target already counted once, then passed after refinery success reset the implementation-only counter; the paired repeated normal-worker partial test still consumes one failure strike.
- [x] 2.6 Clear `ended_at` after resume identity/provider validation and before the first running-state write, so a later reboot rediscovers the same run as unfinished. Completed test-first 2026-08-01: the simulated abrupt-exit regression first retained the stale terminal timestamp, then passed after the resume path removed it; paired watchdog discovery/restart tests remained green.
- [x] 2.7 Persist the cleared terminal timestamp before result recovery can perform external work. The resume path now atomically removes `ended_at` before legacy receipt migration or result recovery.
- [x] 2.8 Preserve an unfinished discovered run for explicit restart and consume restart markers only after a successful supervisor launch. Abrupt-stop, pending-discovery, and failed-launch regressions pass.
- [x] 2.9 Track every accepted verified merge-backed receipt, including `PARTIAL`, and preserve the failure budget when suppressing a replayed partial. Current and migrated receipts are canonicalized; the main-loop replay regression passes.
- [x] 2.10 Close the post-stop watchdog-crash identity window, make dry-run observation non-consuming, and report replayed result status accurately. The three focused regressions pass.

## 3. Verification and foldback

- [x] 3.1 Run focused controller tests, lint/format, strict OpenSpec validation, and independent exact-head review. Completed 2026-08-01 on Windows at exact implementation head `0b35c99b`: 191 focused tests passed, Ruff and strict OpenSpec were clean, and opposite-provider Claude review returned `APPROVE`.
- [ ] 3.2 Re-run focused tests/lint/strict OpenSpec and exact-head review, land through a reviewed PR, restore the original `drain-20260801-113628-6deab6` run, prove its existing claim resumes automatically, then sync/archive and retire the STATUS row. Earlier admission proof remains valid: attempt 33 merged #2103, and attempt 34 admitted and merged the bounded owner-gate slice as #2106 before the restart identity regression surfaced.
