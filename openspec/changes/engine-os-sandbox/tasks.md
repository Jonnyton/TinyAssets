## 1. Contract review gates

- [ ] 1.1 Re-check all three MODIFIED requirement headings by exact match against their canonical specs and run `openspec validate engine-os-sandbox --strict`.
- [ ] 1.2 Obtain opposite-provider review of the closed workload/profile/policy/tier vocabulary, bound policy/projection/egress/credential/authority references, non-fallbackable error taxonomy, and #1784 consumption boundary.
- [ ] 1.3 Reconcile every blocking review finding without adding a distributed-execution delta or restating provider authority.

## 2. Owner handoffs

- [ ] 2.1 Hand the concrete backend-to-profile/tier binding and additive in-process `RunnerCapabilities.isolation_tier` decision to `distributed-execution`, preserving both frozen runner wire versions and all existing `JobCapability` values.
- [ ] 2.2 Hand scoped egress to `outbound-boundary-layer` and ambient credential isolation to `credential-vault`; neither may be represented as complete in this lane.
- [ ] 2.3 Hand authoring false-attestation A0 to the active node-authoring owner so `requires_os_isolation` refuses until a real admitted backend binding exists.
- [ ] 2.4 Confirm #1784 and its three provider-authority successors retain sole ownership of authority, immutable invocation/executor integration, background/requester-host activation, and B2/B13 accepted-market pre-routing.

## 3. Implementation-lane prerequisites

- [ ] 3.1 Before any runtime work, create separately claimed implementation rows with exact file boundaries and refresh provider-context at build phase.
- [ ] 3.2 Require tests that mutation-prove diagnostic-only status, no Codex dangerous bypass, immutable trusted-callsite derivation, terminal admission errors, tool-denied inference, closed projections, and runner-backed graph/NodeBid `source_exec`.
- [ ] 3.3 Require distributed-execution evidence for every backend-to-tier/profile binding before enabling the corresponding workload.
- [ ] 3.4 Keep implementation, build, canonical spec sync, archive, deployment, live acceptance, and post-fix monitoring outside this spec-only rewrite.
