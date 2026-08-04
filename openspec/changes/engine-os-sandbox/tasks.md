## 1. Contract review gates

- [x] 1.1 Re-check the RENAMED source heading's `FROM` plus the two unchanged MODIFIED headings by exact match against canonical specs, verify the `TO` heading is internally consistent, and run `openspec validate engine-os-sandbox --strict`.
- [x] 1.2 Obtain opposite-provider review of the closed workload/profile/guarantee vocabulary, owner-defined references, owner-native carrier split, sealed outer-capsule requirement, shared admission-error taxonomy, and #1784/B2/B13 consumption boundaries.
- [x] 1.3 Reconcile every blocking review finding without adding a distributed-execution delta or restating provider authority.

## 2. Owner handoffs

- [x] 2.1 Hand the static `BackendProfileBindingV1`, fresh admission- and full-request-bound `BackendPreflightEvidenceV1`, sealed `ExecutionAdmissionCapsuleV1`, and exact-property/result/cleanup `BackendLaunchEvidenceV1` to `distributed-execution`, preserving the frozen inner runner versions and all existing `JobCapability` values in this lane.
- [x] 2.2 Hand owner-defined egress and credential requirement references/digests to `outbound-boundary-layer` and `provider-credential-custody`; neither taxonomy or compatibility matrix may be represented as complete in this lane.
- [x] 2.3 Hand authoring false-attestation A0 to the active node-authoring owner so `requires_os_isolation` refuses until a real admitted backend binding exists.
- [x] 2.4 Confirm #1784 and its three provider-authority successors retain sole ownership of authority and activation: ordinary provider work binds through `ProviderInvocation`/`ProviderExecutor`, while accepted-market work binds through B2/B13 before ordinary routing.

## 3. Implementation-lane prerequisites

- [x] 3.1 Before any runtime work, create separately claimed implementation rows with exact file boundaries and refresh provider-context at build phase.
- [ ] 3.2 Require tests that mutation-prove diagnostic-only status, no Codex dangerous bypass, immutable trusted-callsite derivation, shared terminal admission errors across provider/runner/B2 paths, tool-denied inference, closed projections, sealed capsule binding, pre-launch capability/configuration proof without future-launch attestation, post-launch complete-guarantee evidence rejection, and runner-backed graph/NodeBid `source_exec`.
  - A1 contract slice: `ExecutionRequirement` now has closed trusted derivation, immutable fields, and complete opaque owner reference/digest bindings; the remaining cross-owner/runtime clauses keep 3.2 open.
  - A1b contract slice: shared `ExecutionAdmissionError` now exposes exactly the nine closed reasons, rejects unknown-reason mutations, and remains outside `ProviderError`; owner-native mappings remain downstream, so 3.2 stays open.
- [ ] 3.3 Require distributed-execution tests that prove capability and exact planned configuration before launch, then prove the complete request-bound property set for the actual execution before accepting output for every backend/profile binding.
- [ ] 3.4 Keep implementation, build, canonical spec sync, archive, deployment, live acceptance, and post-fix monitoring outside this spec-only rewrite.
