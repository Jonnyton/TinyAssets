# OpenSpec drain blocker freshness audit

Date: 2026-07-29 America/Los_Angeles  
Provider: `drain-20260729-194051-a81d12`  
Base: `origin/main` at `eff97a1e5734bc7166e0381069a713ede0a06743`

## Scope

Freshness-check PR-number dependency labels in `STATUS.md` against GitHub,
current `origin/main`, and named worktrees. Remove only labels contradicted by
current evidence; a merged spec or recovery implementation does not satisfy
its separately named runtime, deployment, host, or acceptance gates.

## Evidence and result

- PR #1899 is the current-main head. It already retired the completed #1880
  drain claim and corrected the bare, landed #1784, #1802, and #1807
  prerequisites visible in the controller's older snapshot.
- PR #1843 is `MERGED` at
  `f06814fb2e7b99bca1b586e44ed068fa7c07a2dc`, and
  `git merge-base --is-ancestor <merge> origin/main` exits 0.
- #1843's body says the recovery is dispatched only after merge with the exact
  image, digest, embedded revision, and unsafe-fence source generation.
  Therefore “#1843 recovery merge/CI” is no longer a valid dependency, while
  preflight, exact-digest deployment, five-container proof, writer fencing,
  rollback safety, receipt stability, and rendered filing remain valid.
- `wf-retire-cheat-live-proof-20260728` still exists on its deleted remote
  branch. Its live recovery/proof work is same-day active and was neither
  reaped nor claimed.
- PRs #1792 and #1819 remain open drafts. Runtime-qualified references to
  merged specification PRs (#1753/#1784) are also still valid because their
  named runtime work has not been inferred from spec landing.

## Correction

Removed only `#1843 recovery merge/CI` from the active recovery row's
dependency cell. No task ownership, live gate, or implementation file claim
changed.

## Reproduction

```powershell
python scripts/claim_check.py --provider drain-20260729-194051-a81d12 --status-ref origin/main --json
gh pr view 1843 --json state,mergedAt,mergeCommit,body,statusCheckRollup,url
git merge-base --is-ancestor f06814fb2e7b99bca1b586e44ed068fa7c07a2dc origin/main
git -C C:/Users/Jonathan/Projects/wf-retire-cheat-live-proof-20260728 status --short --branch
```
