# Design: self-healing merge and release automation

## Decision

Use two independent scheduled reconciliation loops, each with one responsibility:

1. `release-reconcile.yml` remains the sole dead-man repair for merged-but-not-deployed release drift. It reads the canonical build path filter, compares it with successful deploy ancestry, and dispatches `build-image.yml` when production is stale.
2. `auto-enroll-merge.yml` gains a scheduled sweep that asks GitHub for open PR state and calls `gh pr update-branch` for enrolled PRs that are behind `main`.

Both loops are driven by GitHub's scheduler, so their execution does not depend on an event emitted by the `GITHUB_TOKEN` action they are repairing.

## Alternatives considered

### Merge with a PAT or GitHub App token

This would restore ordinary push-triggered workflows, but it introduces a separate write credential and one-time host configuration into a workflow that currently operates with an ephemeral repository-scoped token. `pull_request_target` executes the trusted base workflow, which limits exposure, but the extra credential still expands secret-management and compromise impact. Rejected for this lane.

### Add another post-merge event chain

Rejected. A prior `pull_request_target: closed` repair was suppressed by the same token rule as the push it attempted to replace. Another event chain duplicates a failure mode already observed in production.

### Disable strict branch protection

Rejected. It removes the freshness gate instead of repairing automation. Updating the enrolled branch preserves strict checks and makes the existing repository setting `allow_update_branch: true` useful.

## Failure handling

- The branch sweep is idempotent: a PR is selected only while GitHub reports it `BEHIND`; the next run sees the updated state.
- One PR update failure is reported and does not prevent later candidates from being attempted.
- API or query failure fails the sweep visibly; it does not claim success.
- Release reconciliation remains separate, so branch-update failures cannot disable production drift repair.

## Verification

- A test must fail on the pre-change workflow because it has no scheduled update sweep.
- Tests assert the release reconciler has a schedule, uses successful production deploy ancestry, and dispatches `build-image.yml` on drift.
- Tests assert the auto-enroll sweep selects only open, non-draft, enrolled, `BEHIND` PRs and invokes `gh pr update-branch`.
- `actionlint` must report clean for the touched workflow.
