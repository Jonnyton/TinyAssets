## 1. Apply Gate and Reconciliation

- [ ] 1.1 Stop before runtime work until the two residual gates settle: R2-1a makes every `set_engine` path set `allowed_providers` for the selected engine, and #1691 defines the call-local credential-kind/authority-class evidence contract. #1592 has settled fail-closed universe credential isolation.
  - Premise verification (2026-07-25): **PARTIALLY SETTLED — BLOCKED.** #1592 merged and deployed as `ec5e7b11`, satisfying fail-closed universe credential isolation. The remaining `set_engine` paths write engine selection/preferences but never `allowed_providers`, and `ProviderResponse` still carries no credential-kind or authority-class evidence; R2-1a and #1691 therefore remain apply gates.
- [x] 1.2 Rebase on current `origin/main`, reread the canonical `provider-routing` and `credential-vault` specs plus owning source, and update this change before implementation if the blocker altered any receipt semantics.
  - Reconciliation (2026-07-25): **COMPLETE ON THE USER-FIXED BASE `92d730bc`.** The landed credential-vault contract now builds universe children from an empty environment, admits only provider-specific overlays, and fails closed with sanitized errors. That settles the isolation conjunct without changing this change's result-local receipt shape: authority evidence must still be captured at the exact credential-resolution/provider-execution boundary. The delta, proposal, and design now name only the residual R2-1a `allowed_providers` and #1691 authority-class gates. PR #1549 closed on 2026-07-25; its mutable `str`-subclass receipt is contract-incompatible with this immutable result-local design and was not adopted.
- [ ] 1.3 Broaden the STATUS Files boundary through `claim_check.py --check-files` before touching runtime or tests; do not treat this spec-only lane as implementation ownership.
  - Contract check (2026-07-25): **NOT TRIGGERED — REMAINS A FUTURE APPLY GATE.** This pass touched only the named OpenSpec documents. It did not run `claim_check.py`, broaden STATUS ownership, or edit runtime/tests, so this spec-only lane still claims no implementation ownership.

## 2. Result-Local Provider Contract

- [ ] 2.1 Add failing focused tests for the immutable result/receipt shapes, exact `call_provider(...) -> str` compatibility, result-local provider/model/family evidence, stable credential-kind and authority-class enums, and absence of secret-bearing fields.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** Current focused tests cover only the legacy string bridge; no immutable receipt/result or typed authority/redaction tests exist.
- [ ] 2.2 Add the result-returning bridge path and immutable receipt/attempt types, make the legacy string operation delegate to it, and ensure no receipt field reads `_last_provider` or any other global last-call state.
  - Premise verification (2026-07-25): **LIVE — BLOCKED BY 1.1.** Current `tinyassets/providers/call.py` returns `str` directly and populates process-global `_last_provider`; there is no result-returning bridge. PR #1549 closed on 2026-07-25 with a contract-incompatible mutable `str`-subclass receipt design and must not be revived or duplicated.
- [ ] 2.3 Thread credential kind and authority class from the exact auth-resolution/provider-execution boundary through the same provider response, including explicit `unknown`, `local`, and `none` semantics and the ban on host authority for a universe-scoped remote success.
  - Premise verification (2026-07-25): **LIVE — BLOCKED BY 1.1.** #1592's landed credential-vault contract closes the partial-overlay and swallowed-error host-authority leaks, but `ProviderResponse` still has no credential or authority fields. R2-1a still owes selected-engine `allowed_providers`, and #1691 still owes the call-local authority-class enum/evidence contract.
- [ ] 2.4 Aggregate redacted ordered attempts across all bounded retry waves and attach the immutable receipt to exhaustion and other observed error paths without changing existing exception identity or retry behavior.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** Router diagnostics currently omit successes and retry ordinals, retain mutable/raw `detail`, and the bridge does not aggregate earlier Tenacity waves or attach a result-local receipt.
- [ ] 2.5 Represent provider success, explicit fallback, forced mock, the exhausted-judge degraded sentinel, exhaustion, and unrelated-error outcomes plus the independent missing-router/exhaustion/provider-error route conditions without attributing synthetic text to a provider, model, family, credential, or authority.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** These paths still return/raise legacy values without receipts; the judge sentinel remains a synthetic `ProviderResponse(provider="none", model="quality-floor-only")`.

## 3. Reply and Learning Integration

- [ ] 3.1 Add failing tests that interleave provider calls and universe turns, proving distinct call IDs, no cross-call evidence bleed, and independent `reply` and `learning` receipts regardless of completion order.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** No call-ID, interleaving, or per-phase receipt tests exist on current `main`.
- [ ] 3.2 Add a result-aware universe-intelligence turn path that retains the reply and learning-extraction receipts separately while preserving `converse(...) -> str` and the non-fatal learning-failure behavior.
  - Premise verification (2026-07-25): **LIVE — BLOCKED BY 1.1.** `converse(...)` and `extract_learning(...)` both consume plain strings and retain no result-local evidence. Closed PR #1549's overlapping mutable receipt implementation remains contract-incompatible.
- [ ] 3.3 Verify both `converse` writer calls use the explicit phase and result-aware bridge path, and that a learning failure cannot overwrite or relabel the receipt for the founder-facing reply.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** Both calls use `call_provider(...)` without a phase argument; existing tests prove only sandboxing and non-fatal learning failure.

## 4. Sink Boundary and Verification

- [ ] 4.1 Prove the implementation performs no receipt persistence, structured logging, run-receipt write, wiki/history write, or MCP response change; if a sink is requested, stop and create a separate OpenSpec change with ownership, ACL, retention, correlation, sizing, redaction, and failure semantics.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** Current `main` has no new receipt implementation or sink, but that vacuous baseline cannot prove the side-effect behavior of code that is not yet allowed to be built.
- [ ] 4.2 Run focused provider-call and universe-intelligence tests plus the full relevant regression set and `ruff check` on every touched Python file.
  - Premise verification (2026-07-24): **LIVE — BLOCKED FOR COMPLETION.** Baseline evidence is clean (`44 passed`; Ruff clean), but no Python implementation was permitted, so the post-implementation verification required by this task cannot run.
- [ ] 4.3 Obtain independent correctness, concurrency, compatibility, and secret-redaction review; resolve all blocking findings before treating implementation as complete.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1.** There is no permitted implementation diff to review; cross-family review remains a pre-PR gate.
- [ ] 4.4 Sync this delta into the canonical `provider-routing` spec and archive the change only when implementation, tests, and review have landed together.
  - Premise verification (2026-07-24): **LIVE — BLOCKED BY 1.1–4.3.** Sync/archive would falsely publish unimplemented requirements and is intentionally deferred.
