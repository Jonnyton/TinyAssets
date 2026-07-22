# Research: Stale Auto-PR Queue Cleanup Patterns

**By:** cowork-vision
**Date:** 2026-05-05T00:55Z
**Context:** Workflow has a 7-PR stale-substrate cluster (#277-#282, #286). All show -238/+5 destructive-deletion signature on BUG-058 substrate. Looking for substrate patterns to handle this class durably.

## 1. Renovate's Auto-Rebase

`rebaseWhen` config controls behavior:
- **`behind-base-branch`** or **`:rebaseStalePrs` preset** — auto-rebase any open PR once it falls behind base. **Best fit for Workflow's auto-change PRs.**
- `auto` + `automerge: true` — most aggressive, rebases before every merge attempt
- `conflicted` — only on actual merge conflicts
- `never` — manual

Renovate watches HEAD of base branch each cycle (~hourly). On divergence, reapplies PR's changes as new commit (not git-rebase).

## 2. Dependabot's 30-Day Cutoff

- Auto-rebases by default
- **Stops after 30 days of inactivity** (baked in, no flag to disable)
- Manual: `@dependabot rebase` comment triggers rebase
- Community: `gha-auto-dependabot-rebase` GitHub Action listens for base-branch pushes + auto-comments `@dependabot rebase` on stale Dependabot PRs

## 3. `actions/stale` + Merge Queue

`actions/stale` (native GHA):
- `days-before-stale: 60` — marks "Stale" label
- `days-before-close: 7` — auto-close if no activity since label
- Activity (comment/commit) clears label + resets timer
- **Best practice: triage only, not auto-close.** Label + comment with context, let humans decide.

Merge queue (via repo settings):
- "Require branches to be up to date before merging" forces re-CI on combined state
- Catches build regressions but not logic regressions

## 4. Cluster-Regression Detection (the hard problem)

Standard merge conflict detection ≠ semantic correctness. Tools that go further:

- **git-regress** (TonyStef/git-regress) — detects semantic regressions across PRs that git's conflict detection misses. Requires custom CI integration.
- **GitHub merge queue** — `merge_group` event re-runs required checks on combined state.
- **Manual diff audit**: spot-check `git log --oneline main..pr` for silently-reverted commits.

## Actionable Substrate for Workflow

1. **Auto-rebase loop-produced stale PRs:** add a Workflow primitive (`auto-change/*` branches get auto-rebased on base advance). Pattern: substrate watcher fires on main push, walks open PRs with `auto-change/` prefix, rebases each in order. Equivalent to Renovate's `rebaseWhen: "behind-base-branch"`. Combined with PR #284's stale-base guard, prevents both creation-from-stale-base AND ongoing-stale-while-open.

2. **Triage-only stale labeling:** `actions/stale` for PRs older than 90 days, label only (no auto-close), human decides. Reframe held-too-long as queue-quality signal, not auto-action.

3. **Pre-merge cluster regression check:** for clusters of PRs sharing a common base, validate merging-each-against-latest-main wouldn't revert recent commits to the same files. Workflow already has `_regression_diff_violations()` from PR #297 — extend it to fire as a *queue-merge guard* (when merging PR-N, validate against PR-(N-1) post-merge state, not just current main).

4. **Specific to current 7-PR cluster:** the cleanest path is to land PR #297 first (regression detector), then re-rebase each held PR. Once rebased against post-#297 main, each one's destructive-deletion signature disappears (they pick up the BUG-058 substrate as part of the new base) — and PR #297's gate validates the result.

## Sources

- Renovate: Updating and Rebasing branches docs
- GitHub: Dependabot dependency-updates docs
- GitHub Actions: Close Stale Issues marketplace listing
- git-regress: TonyStef/git-regress
- GitHub April 2026 Merge Queue Incident discussion #193645
- GitHub: Managing a merge queue docs

## Cross-references

- PR #297 (regression detector) — once landed, IS the cluster-regression guard for Workflow
- PR #284 (stale-base guard) — prevents creation; complements auto-rebase
- BUG-061 (cluster-regression class observation, filed earlier today)
- Codex's 23:46Z + 00:25Z queue-fairness/Actions-env signals
