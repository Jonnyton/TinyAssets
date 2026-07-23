## Context

PR #1622 synced nine shipped capability contracts, then merged before its claimed independent reviews were durably present. A post-merge source-and-test audit found two bounded specification defects: the GitHub pull-request adapter checks its operator kill switch before it checks destination presence, and the provider bridge retries by exception type rather than by a proven transient/permanent classification. The same audit therefore cannot continue to claim that every canonical requirement has passed independent grounding.

This is an authority correction, not a runtime change. The controlling evidence is `tinyassets/effectors/github_pr.py`, `tinyassets/providers/call.py`, their focused tests, and the full-coverage audit.

## Goals / Non-Goals

**Goals:**

- Make both canonical requirements state the exact shipped ordering and retry boundary.
- Preserve every unaffected scenario and limitation in the two full requirement blocks.
- Make the audit distinguish verified syntax/focused-test evidence from independent code-grounding approval.
- Keep the correction reviewable and reversible as a documentation-only OpenSpec change.

**Non-Goals:**

- Change runtime behavior, environment-variable semantics, retry counts, wait intervals, APIs, or storage.
- Decide whether permanent provider exhaustion ought to be retried in a future implementation.
- Claim that a Codex post-merge review satisfies the project's required opposite-provider review gate.
- Repair other security limitations recorded by the post-merge audit.

## Decisions

### Specify execution order, not an abstract safety outcome

The external-effect requirement will explicitly order matching-packet selection, the global operator kill switch, and destination validation. This is preferable to saying only that both paths are dry runs because their evidence phases and reasons are observably different. An alternative was to change runtime order so missing destination always wins; that would be a behavior change and is outside this corrective lane.

### Describe retry eligibility by the exception contract

The provider requirement will say that every `AllProvidersExhaustedError` is retry-eligible for up to three total attempts, regardless of whether its underlying cause is transient or permanent, while unrelated exceptions receive one attempt. This matches the `tenacity.retry_if_exception_type` boundary. An alternative was to enumerate transient causes and infer their retryability, but the router does not expose or enforce that classification at this bridge.

### Downgrade audit certainty without discarding valid evidence

The audit will retain strict-validation counts, inventories, source anchors, and focused-test results, but will stop asserting that all 231 requirements and 642 scenarios were independently grounded or BUILT as written. The post-merge findings will be named explicitly, and completion criterion 5 will remain failed until the corrected authority set receives the required durable review.

## Risks / Trade-offs

- **[Risk] A document-only correction could hide a desirable runtime improvement.** → Record retry policy improvement as a separate future behavior decision rather than smuggling it into an as-built correction.
- **[Risk] Renaming a requirement while modifying it could lose scenarios during archive.** → Include the full requirement block in the delta and run strict validation plus post-sync inspection before archive.
- **[Risk] Audit counts may drift as other lanes land.** → Change only the certainty claims implicated by the review and freshness-stamp the correction; do not recompute unrelated inventories in this lane.

## Migration Plan

1. Validate the proposal, design, and two delta specs strictly.
2. Obtain an independent review against source, tests, and audit wording.
3. Apply the approved wording to the two canonical specs and audit.
4. Re-run strict validation and focused tests, inspect the synced requirements, then archive the change.
5. Keep the PR draft until the project-required opposite-provider review is available.

Rollback is a revert of the documentation-only commit; no runtime or data migration is involved.

## Open Questions

- Should a future behavior change avoid retrying exhaustion that is provably permanent? That policy is intentionally deferred.
