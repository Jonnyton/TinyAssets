## Why

The independent post-merge review of PR #1622 found two canonical requirements that overstate or misdescribe shipped behavior, while the associated full-coverage audit claims stronger independent grounding than the evidence supports. Correcting those authority surfaces now prevents future implementation and review work from treating inaccurate prose as as-built truth.

## What Changes

- State that the operator kill switch takes precedence over GitHub pull-request destination validation, so a missing destination may still produce the Phase-2 kill-switch result.
- Describe provider-call retries as exception-type behavior: every `AllProvidersExhaustedError` is retried up to three attempts, including permanent policy, allowlist, pinned-provider, credential, and no-eligible-provider exhaustion; unrelated exceptions are not retried.
- Downgrade the full-coverage audit's independent-review and all-requirements-built certainty until these corrections receive durable review.
- Make no executable runtime or public API change; correct the stale provider-call docstring while existing source and focused tests demonstrate the behavior being specified.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `external-effect-adapters`: Correct the GitHub pull-request gate ordering to give the operator kill switch precedence over missing-destination handling.
- `provider-routing`: Correct the exhaustion-retry contract to match exception-class-based retries rather than claiming transient-only retries.

## Impact

This change modifies two canonical OpenSpec requirements, the provider-call docstring, and the 2026-07-22 full-coverage audit. It does not modify executable runtime behavior, public interfaces, storage, dependencies, or tests. The change is based on merged PR #1622 and is stacked on the approved PR #1621 legacy-authority correction so the coordination and correction lanes remain ordered.
