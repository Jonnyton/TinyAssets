## Why

The local OpenSpec drain can publish a non-draft pull request and let repository
auto-merge complete before an independent exact-head review exists. PR #1884
demonstrated the failure: review found defects only after merge, requiring
follow-up PR #1888.

## What Changes

- Require drain-created pull requests to carry a durable independent-review
  receipt for the exact current head before trusted auto-enrollment enables
  merge.
- Disable an existing drain auto-merge request when a new commit makes the
  recorded review head stale.
- Make the repository's existing required `policy` check fail for a drain head
  without a matching approval receipt, closing the merge race while enrollment
  cancellation is still running.
- Require drain workers to create draft pull requests, obtain independent
  exact-head approval, record the receipt, and only then mark the pull request
  ready for repository-managed auto-merge.
- Preserve the existing enrollment behavior for non-drain pull requests.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `development-coordination-runtime`: make independent review a mechanically
  enforced pre-merge condition for controller-admitted drain pull requests.

## Impact

The change affects the drain worker brief, the trusted auto-enroll and required
scope workflows, a small review-receipt validator, and focused tests. It adds
no dependency, product API, production runtime, or public connector behavior.
