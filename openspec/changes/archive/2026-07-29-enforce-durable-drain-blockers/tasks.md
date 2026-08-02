## 1. Make Blocker Classification Inspectable

- [x] 1.1 Add failing snapshot tests for complete canonical blocked-target extraction, including malformed payload and bounded-hint independence; minimally expose the derived blocked target set on `CandidateSnapshot`.
  - **Verify:** focused snapshot tests fail before implementation and pass after it.

## 2. Enforce Durable Results

- [x] 2.1 Add failing result-path tests proving claimable, missing, and refresh-failed targets reject `BLOCKED`, while an exact current-main blocked target is accepted; minimally implement fail-closed validation that retains admission and consumes the existing finite failure budget.
  - **Depends:** 1.1.
  - **Verify:** red/green tests assert state, admission, recent blockers, and diagnostics.
- [x] 2.2 Add failing prompt and dispatch tests for durable-blocker instructions and recent-blocked hint exhaustion; minimally suppress only the no-hint write dispatch caused by recent-block filtering while preserving owned, alternative-candidate, and true-exhaustion paths.
  - **Depends:** 2.1.
  - **Verify:** red/green tests prove zero peer dispatch during cooldown and unchanged dispatch for every preserved path.
- [x] 2.3 Add canonical-PR replay tests after the live drain counted PR #1879 more than once; persist every receipt for the bounded run, reconstruct only audit-proven canonical legacy receipts on resume, reject duplicate `MERGED` results without advancing slice count, and make bounded target slugs collision-resistant.
  - **Depends:** 2.2 and live attempts 6-7 evidence.
  - **Verify:** red/green unit and run-path tests prove one verified PR advances at most one slice across restart.

## 3. Verify, Review, And Deploy Safely

- [x] 3.1 Run the focused supervisor/watchdog suites, Ruff, strict OpenSpec validation, and a controlled run-directory simulation; obtain opposite-provider exact-head review or the approved same-provider fallback under the AGENTS.md hard-limit rule, then resolve every blocking finding.
  - **Depends:** 2.3.
  - **Verify:** fresh commands and review artifact identify the exact commit.
  - **Completed 2026-07-29:** Claude CLI and Claude.ai (Opus and Sonnet) reported the account-wide monthly spend limit, so the host approved fresh-context independent Codex review. Five reviews found concrete receipt, ambiguous recovery, collision, migration, punctuation-identity, and proposal-scope blockers. Exact rebased head `be33e410` received final independent APPROVE with 167 tests, Ruff, strict validation, OpenSpec flow, dry-run, and GitHub checks green; squash merge `0b155d7c`.
- [x] 3.2 After merge and only after the live controller's active attempt is terminal, deploy the exact merged commit, restart once, verify green health plus durable/invalid blocker probes, sync/archive the change, retire its STATUS row, and record the significant-task reflection.
  - **Depends:** 3.1 and merged PR.
  - **Verify:** deployed commit, watchdog status, run artifacts, canonical spec, and git history agree.
  - **Completed 2026-07-29:** old run stopped gracefully at 15 attempts / 10 reported slices; clean detached controller deployed squash `0b155d7c`, scheduled tray retained, fresh watchdog `drain-20260729-171925-6b1b07` became healthy with zero slices, and the exact merged tree passed 167 focused blocker/replay tests plus Ruff and strict validation before archive.
