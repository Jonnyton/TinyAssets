## 1. Apply Gate and Reconciliation

- [ ] 1.1 Stop before runtime work until #1606 / R2-1a has landed or an explicitly named successor has settled fail-closed universe credential isolation, selected-engine `allowed_providers`, and call-local credential/authority evidence.
- [ ] 1.2 Rebase on current `origin/main`, reread the canonical `provider-routing` and `credential-vault` specs plus owning source, and update this change before implementation if the blocker altered any receipt semantics.
- [ ] 1.3 Broaden the STATUS Files boundary through `claim_check.py --check-files` before touching runtime or tests; do not treat this spec-only lane as implementation ownership.

## 2. Result-Local Provider Contract

- [ ] 2.1 Add failing focused tests for the immutable result/receipt shapes, exact `call_provider(...) -> str` compatibility, result-local provider/model/family evidence, stable credential-kind and authority-class enums, and absence of secret-bearing fields.
- [ ] 2.2 Add the result-returning bridge path and immutable receipt/attempt types, make the legacy string operation delegate to it, and ensure no receipt field reads `_last_provider` or any other global last-call state.
- [ ] 2.3 Thread credential kind and authority class from the exact auth-resolution/provider-execution boundary through the same provider response, including explicit `unknown`, `local`, and `none` semantics and the ban on host authority for a universe-scoped remote success.
- [ ] 2.4 Aggregate redacted ordered attempts across all bounded retry waves and attach the immutable receipt to exhaustion and other observed error paths without changing existing exception identity or retry behavior.
- [ ] 2.5 Represent provider success, explicit fallback, forced mock, exhaustion, and unrelated-error outcomes plus the independent missing-router/exhaustion/provider-error route conditions without attributing synthetic text to a provider, model, family, credential, or authority.

## 3. Reply and Learning Integration

- [ ] 3.1 Add failing tests that interleave provider calls and universe turns, proving distinct call IDs, no cross-call evidence bleed, and independent `reply` and `learning` receipts regardless of completion order.
- [ ] 3.2 Add a result-aware universe-intelligence turn path that retains the reply and learning-extraction receipts separately while preserving `converse(...) -> str` and the non-fatal learning-failure behavior.
- [ ] 3.3 Verify both `converse` writer calls use the explicit phase and result-aware bridge path, and that a learning failure cannot overwrite or relabel the receipt for the founder-facing reply.

## 4. Sink Boundary and Verification

- [ ] 4.1 Prove the implementation performs no receipt persistence, structured logging, run-receipt write, wiki/history write, or MCP response change; if a sink is requested, stop and create a separate OpenSpec change with ownership, ACL, retention, correlation, sizing, redaction, and failure semantics.
- [ ] 4.2 Run focused provider-call and universe-intelligence tests plus the full relevant regression set and `ruff check` on every touched Python file.
- [ ] 4.3 Obtain independent correctness, concurrency, compatibility, and secret-redaction review; resolve all blocking findings before treating implementation as complete.
- [ ] 4.4 Sync this delta into the canonical `provider-routing` spec and archive the change only when implementation, tests, and review have landed together.
