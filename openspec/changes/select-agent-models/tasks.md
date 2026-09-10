## 1. Reviewed foundation

- [ ] 1.1 Resolve the design's exact storage/authority and discovery seams; obtain one cross-family shape review before implementing public/storage/authority changes.
- [x] 1.2 Ship truthful HTTP answering-model receipts, preserving requested selection and unknown metadata behavior, with tests and independent review.
- [ ] 1.3 Implement normalized account-scoped discovery with source/freshness/capability/cost evidence; prove refresh adds a new model and cannot widen endpoint grants.

## 2. Owner policy and execution

- [ ] 2.1 Add versioned universe-local policy and current-choice input through authenticated app ingress; test generation conflicts, isolation and legacy-pin preservation.

  September10 partial: saved preferences/CAS and authenticated unpowered GET/POST
  implemented;352 Windows and352 actual Docker Linux checks pass, zero skips.
  See saved-preferences.md and docs/reviews/2026-09-10-model-preferences-proof.md.
  Current-choice ingress and runtime consumption are still pending; do not mark
  this task complete or expose enabled UI before those pieces work.

- [ ] 2.2 Implement deterministic automatic ranking and ordered explicit fallback within fresh authority, required capabilities and permitted cost; test unscored/stale catalogues and no-paid-fallback.
- [ ] 2.3 Integrate typed capacity scopes and safe continuation into the existing router; prove account exhaustion skips siblings and completed/ambiguous tools are not replayed.
- [ ] 2.4 Resolve the shared HTTP engine-tool-loop prerequisite and prove actual authorized tools work before enabling HTTP full-agent selection.

  September10 partial: synchronous HTTP lookup/request/cleanup now runs in one
  owned executor Future. Cancellation drains it before router settlement; actual
  asyncio.run teardown and selected-authority slot/budget retention are tested.
  Claude implementation APPROVE224s. Legacy-only extraction is draft PR3718;
  this feature branch remains unshipped. HTTP tool calls/results, canonical MCP
  execution and durable safe continuation remain required. See
  http-inference-lifecycle.md. Do not mark full-agent selection complete.

## 3. User proof and delivery

- [ ] 3.1 Build the clickable active-provider/model control with switch, saved default and fallback ordering; test keyboard access, actual-versus-preferred labels and unpowered use.
- [ ] 3.2 Run focused cross-platform tests, independent exact-head review and CI; deploy and verify authenticated SHA/canary evidence, then ordinary rendered app use without operator workflow edits.
- [ ] 3.3 Sync only shipped behavior into main specs and archive this change after completion; update the goal's stage and record any remaining capability gap honestly.
