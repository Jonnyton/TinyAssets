## 1. Target And Authority Gates

- [x] 1.1 Reconcile the #1784 successor handoff, current PLAN modules, five owning capabilities, active paid-market changes, operator Request/BranchTask contract, and current connector/provider/runtime seams; keep this successor accepted-market-only.
- [x] 1.2 Run the primitive collision check and name the connector action exactly `write_graph(target="engine", action="activate_accepted_market")`, with no new handle, overload of the live `target="universe"` birth path, legacy `universe` handle, Request/BranchTask overload, raw secret, desktop prerequisite, or free-form authority.
- [x] 1.3 Write the proposal, design, five capability deltas, and dated current-code/owner audit while granting target authority only.
- [ ] 1.4 Obtain exact-head independent architecture/security/spec reviews and a fresh Claude Opus 5 opposite-provider APPROVE; fold every adaptation into a new exact reviewed SHA.
- [ ] 1.5 Record the host's standing 2026-07-26 acceptance only after the exact reviewers agree the target is fully figured out; stop if a reviewer finds an unresolved host design choice.
- [ ] 1.6 Rebase or merge current `origin/main`, rerun provider-context/claim/collision checks, and publish the target-only draft PR without runtime, payment, deployment, or production authority.

## 2. Required Owner Interfaces

- [ ] 2.1 Land the #1784 accepted-market assignment owner, its atomic agreement/mandate-reference/`remote_ready + []` transaction, fail-safe hold, setup mapping, pre-routing source contract, and TinyAssets current-message reserve/actual-handler-claim/liveness seam without enabling a partial connector path.
- [ ] 2.2 Land live-price selection/evaluation receipts and executable native firm quotes with stable IDs/digests, secure connector read/handoff, and the exact request-bound quote-to-bid, deterministic match, atomic paid claim/fan-out slot, selected host/owner, versions, digests, and fences; none implies capacity, funding, or execution authority.
- [ ] 2.3 Land the paid-market Wave 2 production baseline, tenant workflow, logical budget/accounting transaction, request/bid/match/claim/delivery fences, cancellation, and production-shaped concurrency evidence.
- [ ] 2.4 Land B13 as the sole cross-owner per-job composition coordinator: provisional bounded mandate plus exact allocation/claim, domain-capacity, paid-market logical-accounting, §18.6 real-fund, S14/B36, and B2 binding; do not pre-mint B2 or write another owner's records.
- [ ] 2.5 Land the Engine OS execution-admission implementation and prove that market or B2 authority cannot replace capability, capsule, runner/backend, or sandbox enforcement evidence.
- [ ] 2.6 Land the reviewed wallet/chain-effect successor required by `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6, applicable domain-native capacity owners, and distributed-execution S14/B36 from `docs/exec-plans/active/2026-07-18-distributed-execution-platform.md`; preserve each owner's independent idempotent prepare/commit/cancel and authority.
- [ ] 2.7 Land a paid-market accepted-agreement producer that consumes the canonical request, current quote, and explicit acceptance without reusing request submission, bid, match, claim, or delivery as acceptance; bind all existing request fields server-side.
- [ ] 2.8 Fold the provider-routing reconciliation into #1784 owner truth: activation stores only agreement plus current non-executable mandate references; each concrete `converse` delegates to B13 for fresh per-job B2; no future-job B2 is stored or required by `remote_ready`.

## 3. Connector Schema And Request Identity

- [ ] 3.1 Add the `engine` target and sole `activate_accepted_market` action to canonical `write_graph`, keeping the seven advertised handles and refusing unknown actions, missing/extra fields, coercions, other-target market fields, and unsupported schema versions before mutation.
- [ ] 3.2 Implement the closed `accepted-market-activation/v1` acceptance object with exact request, selection receipt, quote, descriptor, integer-micros budget/spend-cap, currency, fee, demand, acceptance/settlement-policy, deadline, and expiry commitments; enforce the specified ID/key/digest/currency/integer/time grammars and maxima, including `0 < spend_cap_micros <= budget_micros <= canonical_market_max_micros`; forbid actor, tenant, provider, host, credential, wallet, grant, lease, or authority-carrier fields.
- [ ] 3.3 Derive the authenticated principal and tenant only from #1784's TinyAssets current-message reserve, actual registered-handler claim, and live execution lease; mint a distinct one-shot activation capability bound to message/claim/session/tool/target/action/principal/tenant/universe and revoke before result release; reject outer ContextVar-only, inherited/snapshotted FastMCP, prior-message, copied-worker, environment, ProviderRequestCapability, durable-market, or B2 substitution.
- [ ] 3.4 Authorize current subject/tenant/exact-universe and current-message liveness before any replay lookup; return non-enumerating denial after authority loss; domain-separate idempotency as `write_graph/engine/activate_accepted_market`; bind actor/tenant/universe/key/body; prove no request/other-action collision; make same-body replay side-effect stable but separately re-derive current assignment so historical success cannot reactivate or falsely render revoked/held state.

## 4. Paid Agreement And Atomic Activation

- [ ] 4.1 Re-resolve and verify the canonical paid request, route-selection receipt, firm quote, descriptor, explicit acceptance, demand/policy commitments, fee schedule, settlement policy, currency, integer-micros budget and spend cap, deadline, expiry, cancellation, capacity fence, and current actor/tenant/universe at the commit boundary.
- [ ] 4.2 Invoke the canonical tenant-scoped accepted-agreement producer with the rehydrated current request and quote; do not treat request submission, ranking, bids, matches, claims, reservations, payment intent, or a database row as acceptance, money, provider, host, or execution authority.
- [ ] 4.3 Obtain a bounded non-executable provisional B13 market mandate and atomically commit its opaque reference plus the accepted agreement and `engine_source="accepted_market"`, `engine_assignment_state="remote_ready"`, `allowed_providers=[]`; only the committed reference makes the mandate current/discoverable, and every fault or losing race commits none of that activation state.
- [ ] 4.4 Make concurrent first activation single-winner and cover cancellation, quote expiry, capacity loss, fee/version drift, revocation-generation, fence, timeout, and post-commit response-loss retries without duplicate agreement, mandate, reservation, charge, grant, or assignment; idempotently revoke or expire every uncommitted provisional mandate.
- [ ] 4.5 Inventory legacy `market_rented`, raw-key, partial, and inconsistent engine rows; map them to typed held/failed state without automatically promoting or reinterpreting them as accepted-market authority.

## 5. Per-Job Remote Converse

- [ ] 5.1 Before ordinary routing, re-derive agreement/current mandate and exact job demand/quantity; have B13 coordinate the current request-bound quote/bid/match/paid-claim/slot/selected host, domain-fenced capacity, paid-market logical budget reservation, §18.6 requester real-fund result, and S14/B36 identity through owner-native idempotent prepare/commit/cancel interfaces.
- [ ] 5.2 Bind and verify request/bid/match/claim/slot identities, versions, digests, quote-to-bid link, selected host/owner, capacity fence, logical-accounting result, real-fund result, agreement, mandate, quote, demand, quantity, fee/spend ledger, owner, tenant, universe, daemon/host equality with current claimant, job, `job_id:lease_fence:accepted_result_sha256`, capsule, lease, generation/fence, capability ceiling, expiry, revocation, idempotency, and Engine OS admission before external work.
- [ ] 5.3 Dispatch only through the signed remote seam and mutation-test that the ordinary router, provider ceilings/chains, maintainer credentials/quota/wallet/compute, requester-host, local, BYOC, free, desktop, and environment fallbacks are never consulted.
- [ ] 5.4 Serialize claim slot, logical budget, domain capacity, and real-fund resources at their owners; require one fenced `reserved -> dispatch_committed | cancelled_and_released` winner; reuse same-job results/B2; conflict on changed bodies; release cancelled prepares once; after dispatch settle/refund only from current platform-signed B2 terminal plus domain acceptance bound to `job_id:lease_fence:accepted_result_sha256`; host self-attestation is insufficient; downgrade stale authority to `held + []` without widening.
- [ ] 5.5 Return faithful structured and bounded-text success/refusal/conflict/repair results containing safe status and economic summaries only; expose no secret, signature, grant, lease capability, provider credential, host address, wallet token, or internal authority carrier.

## 6. Security, Concurrency, And Regression Tests

- [ ] 6.1 Add connector schema/grammar/boundary/overflow/Boolean-float-string-coercion, unknown-field, action/target isolation, metadata, exact-text-envelope, idempotent replay, changed-body conflict, auth-before-lookup/non-enumeration, historical-success/current-held truth, and no-reactivation tests.
- [ ] 6.2 Add anonymous, cross-actor, cross-tenant, cross-universe, stale-session, mismatched-tool/action, background/deferred/stdio/SSE, serialized capability, outer-ContextVar-only, inherited/snapshotted/prior-message FastMCP, copied-worker, second-claim, stale-liveness, ProviderRequestCapability substitution, and ambient-maintainer-fallback refusal tests.
- [ ] 6.3 Add transaction/fault tests for each owner plus simultaneous activation/job/retry/cancel/dispatch/expiry/claim-slot/capacity/funding/budget/fence/revocation races, proving one activation, no oversubscription, one dispatch-or-cancel winner, exactly-once release/refund/settlement, no host-self-attested settlement, and zero phantom `remote_ready`.
- [ ] 6.4 Add market tests proving accepted agreement, canonical-request rehydration, micros budget/spend, exact quote→bid→match→paid-claim/slot/selected-host binding, paid-market logical-accounting-only ownership, separate domain capacity and §18.6 real-fund ownership, no silent lane substitution, and no evidence promotion.
- [ ] 6.5 Add distributed-execution tests proving mandates are non-executable, B13 writes no owner records, every B2 binds the complete owner-native result set and exact claimant host/job/capsule/S14-B36 identity, non-authoritative receipts cannot be promoted, admission remains mandatory, and ordinary routing is never called.
- [ ] 6.6 Add setup/refusal/repair/downgrade tests for every lifecycle cause and prove only connector-completable accepted-market actions are advertised.

## 7. Dark Rollout And User Proof

- [ ] 7.1 Keep the action unadvertised as completable and global enforcement dark until every owner interface and test above is live; permit only server-owned default-empty isolated test principals/universes after preflight.
- [ ] 7.2 Define and run the full-platform architecture section-14 numerical load envelope for concurrent quote evaluation, activation, replay, cancellation/expiry/revocation/fence, first `converse`, saturation, failure injection, and recovery; record commands, topology, distributions, errors, duplicates/loss, and recovery evidence.
- [ ] 7.3 Run canonical `/mcp` public canaries and a real rendered chatbot conversation in which a newborn Tier-1 user sees current terms, explicitly accepts them, activates the exact universe, and completes remote `converse` without maintainer quota or a desktop; record prompt/result plus trace or screenshot.
- [ ] 7.4 Verify post-fix clean user use through privacy-reviewed production evidence; if none exists, leave a dated STATUS watch item rather than claiming proof.
- [ ] 7.5 Obtain explicit rollout approval, remove isolated test registrations, and cut over only after rollback preserves signed/financial evidence, monotonic fences, and held assignments without reinterpreting legacy state.

## 8. Foldback

- [ ] 8.1 Re-run strict OpenSpec, focused/full tests, lint, security, concurrency/load, public canary, rendered-chatbot, and independent exact-diff review at the landing SHA.
- [ ] 8.2 Sync the five deltas into canonical specs, including the #1784 provider-routing clarification, and archive this change only after implementation and production-shaped acceptance are complete.
- [ ] 8.3 Delete the landed STATUS implementation row, retire the worktree lane, and publish final authority, evidence, rollback, and post-fix-use records.
