# Workspace usage diagnosis: independent Claude review

Date: 2026-09-08 PDT / September 9 UTC.
Scope: source interpretation and correction scope in
`docs/concerns/2026-09-08-workspace-hourly-cap-stalls-light-use.md`; **not**
approval of runtime changes or a new resource-accounting architecture.

Command: `python scripts/peer_agent.py claude --out
output/workspace-usage-review-claude.md --prompt-file
output/workspace-usage-review-brief.md --timeout 600`.
Read-only independent cross-family invocation; exit 0 after 330 seconds.
No tests, production access, edits, worktrees or child reviews were performed.

The wrapper's final file captured the later stop-hook response rather than the
substantive review. The actual assistant text was read from the same invocation's
session `ec1cbb23-be4f-42ee-a1ef-28cca7fe231b`, filtering assistant text only.
This file preserves a concise disposition of that review, not a claim that the
wrapper file contains the full analysis.

## Verdict and findings

**VERDICT: ADAPT.** The reviewer agreed with the ten-start refusal, rolling-hour
arithmetic, omitted override plumbing, previous PR #2770 not touching workspace
admission, 300/900 general limits, provider ceilings, conservative failed-checkout
reservation, and universe-local database scope.

| Review item | Disposition |
|---|---|
| `run-usage-budgets` already landed in #2731, despite unchecked tasks; include its 5,000-dispatch / 2 GiB hourly controls | Accepted. Verified commit and production constants; report corrected. Closure bookkeeping still needs a scoped sync/archive, not reimplementation. |
| Permanent workspace storage already has a hard-coded 16 GiB quota | Accepted. Report now names `_universe_quota_kwargs` and distinguishes it from a wired tier policy. |
| Push and discard consume jobs; the zero-byte cleanup counts against ten | Accepted. Current call sites verified and added. |
| `ledger_usage` has no production callers; raw epoch in refusal is poor usage visibility | Accepted as the current visibility gap. No public read surface is implemented in this documentation slice. |
| Raise the constant under the standing earlier usage directive as an interim, plus legible receipt | Considered, not implemented here. It can provide interim relief, but does not satisfy the owner's newer consolidation direction or constitute lane completion. No new threshold has been selected. |

One review inference is **not adopted**: a per-universe rate limit can protect
shared host resources by bounding one user's churn, even though its records are
universe-local. The existing host/pool lock names also do not prove effective
host-global exclusion across separate databases. Therefore the report does not
claim that lifting the jobs gate has no shared-host implications. Retain actual
resource protections and test aggregate admission before calling replacement
accounting safe.

The reviewer identified remaining design decisions: the unit and authority of
shared activity accounting, storage attribution, treatment of push/discard, byte
throughput, and cross-universe owner aggregation. One related reviewer sentence
suggested push moves no new dependency bytes; that is not accepted literally—a
push transports a bundle. Cleanup and network writes need distinct measured-cost
treatment, not a blanket zero-cost classification.

Post-review source/synthetic verification also qualifies "HTTP dispatch budget":
`dispatch_node_effects` counts every node with effects, including workspace,
once before iterating its sinks. The generic byte meter counts only delivered
results, so ordinary workspace transfer bytes remain separate. The incident
report carries the exact synthetic probe command and result. Thus the review's
three-budget-family conclusion holds, but the families overlap more than its
HTTP-only shorthand implies.

## Acceptance boundary

Owner subsequently reiterated that Patches remains open. New rendered
repository-write and heartbeat-retirement evidence is recorded separately in the
checklist report with its exact scope. Those successes do not close the hourly
workspace incident, the simpler activity/storage design, or owner acceptance.
