## Context

The drain supervisor delegates the complete delivery lifecycle to one
write-capable worker. Its brief requires independent review, but the repository's
trusted `auto-enroll-merge.yml` enrolls every same-repository, non-draft pull
request as soon as it opens. A worker that opens a ready pull request before
review can therefore merge as soon as CI passes. PR #1884 did so; PR #1888 was
needed to repair defects found by the later review.

Drain admissions already use a recognizable `drain/<run>/<target>-<attempt>`
branch namespace. The trusted `pull_request_target` workflow runs from default
branch code and can therefore enforce a drain-specific enrollment contract
without executing untrusted pull-request code.

## Goals / Non-Goals

**Goals:**

- Keep every `drain/*` pull request out of auto-merge until an independent
  review approves its exact current head.
- Cancel stale auto-merge enrollment when a reviewed drain pull request gains a
  new commit.
- Keep ordinary same-repository pull-request enrollment unchanged.
- Make the contract small, deterministic, and testable without a new service or
  dependency.

**Non-Goals:**

- Cryptographically prove that two different model processes produced the
  implementation and review.
- Change branch protection, GitHub account permissions, or non-drain review
  policy.
- Add a new terminal drain result or split one delivery across multiple pull
  requests.
- Change the future user-owned cloud drain architecture.

## Decisions

### Use an exact-head receipt in the pull-request body

A drain pull request is eligible for auto-enrollment only when its body contains
exactly one of each marker:

```text
Drain-Review-Verdict: APPROVE
Drain-Review-Head: <40-character lowercase Git commit SHA>
Drain-Review-Artifact: <docs/*.md path or https://github.com/... URL>
```

The recorded head must equal GitHub's current `headRefOid`. Exact markers keep
the interface inspectable by humans, reusable across providers, and independent
of private local controller state.

Alternatives rejected:

- A label is too weak because it carries no exact-head binding and can remain
  after new commits.
- A GitHub approving review cannot represent current opposite-provider review
  reliably because the agents commonly operate through the same repository
  account.
- Prompt text alone already failed in #1884.

### Put the decision logic in a small stdlib validator

`scripts/drain_review_gate.py` validates the branch, head, and body. Non-drain
branches return `allow`; drain branches fail closed on missing, duplicate,
malformed, or stale markers, including a valid marker accompanied by a malformed
marker with the same prefix. The workflow supplies GitHub event data to the
validator and treats any validator error as `deny`.

Keeping parsing out of shell avoids quoting ambiguity and makes exact failure
cases easy to test. No dependency is added.

### Reconcile enrollment on every relevant pull-request event

The trusted workflow listens to `opened`, `reopened`, `ready_for_review`,
`synchronize`, `edited`, `labeled`, and `unlabeled`.

- `allow`: preserve the current idempotent auto-enrollment behavior.
- `deny`: if auto-merge is already enrolled, disable it; otherwise leave the
  pull request unenrolled.

The `synchronize` path is load-bearing: GitHub can retain an existing auto-merge
request across new commits, so merely refusing a second enrollment would not
close the stale-review race. Enrollment additionally passes the reviewed
`headRefOid` through GitHub's matching-head option so a push between validation
and enrollment fails atomically. The privileged workflow pins its checkout
action to the repository's reviewed immutable v4 commit instead of a mutable
tag.

### Reuse the existing required scope check as the merge-atomic gate

Enrollment cancellation alone is reactionary: a newly pushed head can retain
its prior auto-merge request until the `synchronize` handler disables it. The
repository's existing `Diff scope declared` check is already required by branch
protection, so it runs the same validator against the current head and fails on
`deny`. GitHub therefore keeps a new head unmergeable while the check is pending
and after a stale receipt makes it red.

The scope workflow already uses `pull_request_target`; it checks out only the
immutable base SHA, never checks out pull-request code, and pins the checkout
action to an immutable commit. Its token remains read-only. Reusing this trusted
required workflow also avoids the bootstrap dead zone caused by changing the
separate required `policy` workflow's event type in the same pull request.
Ordinary branches receive `allow` from the validator and continue through the
existing scope declaration unchanged.

### Make draft-first publication explicit in the worker brief

The worker must open its one pull request with `--draft`, obtain independent
review of the exact head, add the receipt, and only then mark it ready. A commit
after review invalidates the receipt and requires another exact-head review.
Workers must not invoke `gh pr merge` directly; the trusted repository workflow
owns enrollment.

## Risks / Trade-offs

- **A cooperative worker can forge body markers or invoke GitHub directly.**
  The local drain is already explicitly not OS-sandboxed; this gate prevents
  accidental ordering failures and makes evidence durable, but it is not a
  malicious-worker authorization boundary. Branch protection, CI, finite scope,
  and review remain required.
- **A malformed receipt leaves a pull request unmerged.** The workflow reports
  the denial and exact expected marker shape; the worker can repair the body
  without changing code.
- **The first pull request cannot be protected by workflow code not yet on
  default branch.** This lane itself must stay draft until its independent
  review is complete; the new gate protects subsequent drain pull requests
  after merge.

## Migration Plan

1. Land the validator, focused tests, trusted workflow reconciliation, worker
   brief, required scope gate, and canonical delta spec in one pull request.
2. Keep this pull request draft until its own exact-head independent review is
   complete, then mark ready under the existing repository policy.
3. After merge, verify the workflow on a synthetic or next real drain draft:
   missing/stale receipts remain unenrolled and a matching approval receipt
   enrolls.
4. Roll back by reverting the merge; ordinary pull-request enrollment never
   changes, and drain pull requests safely remain manually mergeable under
   branch protection if the validator is unavailable.

## Open Questions

None.
