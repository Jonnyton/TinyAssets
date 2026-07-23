# Repair the auto-enroll release chain

## Why

Auto-enroll uses `GITHUB_TOKEN`, so GitHub suppresses the workflow events caused by its eventual merge. A release-relevant merge can therefore produce no push-triggered build. Strict branch protection also leaves other enrolled PRs behind `main`, but no automation updates them, so fully green PRs stall indefinitely.

The first failure already has one host-independent repair on current `main`: `release-reconcile.yml` compares the latest release-relevant commit with successful production deploys every 15 minutes and dispatches `build-image.yml` when they diverge. This change preserves that single repair path and adds the missing reconciliation loop for enrolled branches.

## What Changes

- Specify and test that release drift is repaired by the existing scheduled release reconciler, including explicit dispatch of `build-image.yml` when no successful production deploy contains the release-relevant commit.
- Add a scheduled and manually invocable sweep to `auto-enroll-merge.yml` that updates open, non-draft, auto-merge-enrolled PRs whose merge state is `BEHIND`.
- Keep event-driven enrollment for same-repository PRs unchanged.
- Keep `strict` branch protection enabled and avoid a new PAT or GitHub App credential.

## Impact

- Affected workflows: `.github/workflows/auto-enroll-merge.yml`; read-only contract coverage for `.github/workflows/release-reconcile.yml`.
- New regression tests: `tests/test_release_automation_workflows.py`.
- New capability spec: `release-automation`.
- No production dispatch is performed from this change branch.
