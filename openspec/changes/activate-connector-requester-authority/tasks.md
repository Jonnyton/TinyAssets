## 1. Target And Authority Gates

- [x] 1.1 Reconcile the #1784 successor handoff, current PLAN modules, four owning capabilities, active paid-market changes, operator Request/BranchTask contract, and current connector/provider/runtime seams; keep this successor accepted-market-only.
- [x] 1.2 Run the primitive collision check and name the connector action exactly `write_graph(target="engine", action="activate_accepted_market")`, with no new handle, deprecated `universe` target, Request/BranchTask overload, raw secret, desktop prerequisite, or free-form authority.
- [x] 1.3 Write the proposal, design, four capability deltas, and dated current-code/owner audit while granting target authority only.
- [ ] 1.4 Obtain exact-head independent architecture/security/spec reviews and a fresh Claude Opus 5 opposite-provider APPROVE; fold every adaptation into a new exact reviewed SHA.
- [ ] 1.5 Record the host's standing 2026-07-26 acceptance only after the exact reviewers agree the target is fully figured out; stop if a reviewer finds an unresolved host design choice.
- [ ] 1.6 Rebase or merge current `origin/main`, rerun provider-context/claim/collision checks, and publish the target-only draft PR without runtime, payment, deployment, or production authority.

## 2. Required Owner Interfaces

- [ ] 2.1 Land the #1784 accepted-market assignment, `remote_ready + []`, fail-safe hold, setup mapping, and pre-routing source contract without enabling a partial connector path.
- [ ] 2.2 Land live-price selection/evaluation receipts and executable native firm quotes with stable IDs/digests, current fee/currency/expiry/capacity facts, secure connector read/handoff, and no implied reservation or authority.
- [ ] 2.3 Land the paid-market Wave 2 production baseline, tenant workflow, request/bid/match/claim/delivery fences, cancellation, and production-shaped concurrency evidence.
- [ ] 2.4 Land the B13 production composition root interface for a bounded non-executable activation grant and exact per-job B2 grant creation; do not pre-mint B2 before a concrete job/capsule exists.
- [ ] 2.5 Land the Engine OS execution-admission implementation and prove that market or B2 authority cannot replace capability, capsule, runner/backend, or sandbox enforcement evidence.
- [ ] 2.6 Land the separately owned wallet/chain-settlement authority and a single production transaction boundary capable of committing accepted agreement, activation grant reference, and universe assignment atomically.

## 3. Connector Schema And Request Identity

- [ ] 3.1 Add the `engine` target and sole `activate_accepted_market` action to canonical `write_graph`, keeping the seven advertised handles and refusing unknown actions, missing/extra fields, coercions, other-target market fields, and unsupported schema versions before mutation.
- [ ] 3.2 Implement the closed `accepted-market-activation/v1` acceptance object with exact selection-receipt, firm-quote, descriptor, spend/currency, fee, demand, policy, and expiry commitments; forbid actor, tenant, provider, host, credential, wallet, grant, lease, or authority-carrier fields.
- [ ] 3.3 Derive the authenticated principal and tenant from request-local OAuth context, require exact-universe write/admin authority, and mint a one-shot non-serializable capability bound to request/session/tool/target/action/principal/tenant/universe with no environment fallback.
- [ ] 3.4 Authorize before any replay lookup, bind idempotency to actor/tenant/universe/action plus the canonical body digest, return the original typed result for same-body replay, and conflict on changed-body reuse.

## 4. Paid Agreement And Atomic Activation

- [ ] 4.1 Re-resolve and verify the route-selection receipt, firm quote, descriptor, explicit paid mandate, demand/policy commitments, fee schedule, currency, max total, expiry, cancellation, capacity fence, and current actor/tenant/universe at the commit boundary.
- [ ] 4.2 Invoke the canonical tenant-scoped paid workflow to produce the immutable accepted-agreement result without treating ranking, bids, matches, claims, reservations, payment intent, or a database row as money, provider, host, or execution authority.
- [ ] 4.3 Obtain the current bounded non-executable B13 activation grant and atomically commit its opaque reference plus the accepted agreement and `engine_source="accepted_market"`, `engine_assignment_state="remote_ready"`, `allowed_providers=[]`; every fault or losing race commits none of that activation state.
- [ ] 4.4 Make concurrent first activation single-winner and cover cancellation, quote expiry, capacity loss, fee/version drift, revocation-generation, fence, timeout, and post-commit response-loss retries without duplicate agreement, reservation, charge, grant, or assignment.
- [ ] 4.5 Inventory legacy `market_rented`, raw-key, partial, and inconsistent engine rows; map them to typed held/failed state without automatically promoting or reinterpreting them as accepted-market authority.

## 5. Per-Job Remote Converse

- [ ] 5.1 Before ordinary provider routing, re-derive the accepted agreement and current activation grant for every accepted-market `converse`, build the concrete job/capsule, and ask B13 for its exact current B2 grant.
- [ ] 5.2 Verify owner, tenant, universe, daemon/host, job, capsule digest, lease, generation/fence, capability ceiling, expiry, revocation, idempotency, and Engine OS admission at the distributed-execution sink before external work.
- [ ] 5.3 Dispatch only through the signed remote seam and mutation-test that the ordinary router, provider ceilings/chains, maintainer credentials/quota/wallet/compute, requester-host, local, BYOC, free, desktop, and environment fallbacks are never consulted.
- [ ] 5.4 On absent, expired, revoked, fenced, cancelled, consumed, inconsistent, or unverifiable activation/per-job authority, atomically downgrade stale `remote_ready` to `held + []` and return a typed accepted-market refusal, repair, or renewal result without widening authority.
- [ ] 5.5 Return faithful structured and bounded-text success/refusal/conflict/repair results containing safe status and economic summaries only; expose no secret, signature, grant, lease capability, provider credential, host address, wallet token, or internal authority carrier.

## 6. Security, Concurrency, And Regression Tests

- [ ] 6.1 Add connector schema, unknown-field, action/target isolation, metadata, exact-text-envelope, idempotent replay, changed-body conflict, and auth-before-lookup tests.
- [ ] 6.2 Add anonymous, cross-actor, cross-tenant, cross-universe, stale-session, mismatched-tool/action, background/deferred/stdio/SSE, serialized-capability, and ambient-maintainer-fallback refusal tests.
- [ ] 6.3 Add atomic transaction and fault-injection tests for each owner boundary plus simultaneous activation/retry/cancel/expiry/capacity/fence/revocation races, proving one winner and zero phantom `remote_ready` states.
- [ ] 6.4 Add market tests proving explicit paid mandate, current selection/quote/fee/spend/policy binding, no silent lane substitution, and no promotion of ranking/match/claim/reservation/payment/database evidence.
- [ ] 6.5 Add distributed-execution tests proving activation grants are non-executable, B2 is minted only for the concrete job/capsule, non-authoritative receipts cannot be promoted, per-job admission remains mandatory, and ordinary provider routing is never called.
- [ ] 6.6 Add setup/refusal/repair/downgrade tests for every lifecycle cause and prove only connector-completable accepted-market actions are advertised.

## 7. Dark Rollout And User Proof

- [ ] 7.1 Keep the action unadvertised as completable and global enforcement dark until every owner interface and test above is live; permit only server-owned default-empty isolated test principals/universes after preflight.
- [ ] 7.2 Define and run the PLAN section-14 numerical load envelope for concurrent quote evaluation, activation, replay, cancellation/expiry/revocation/fence, first `converse`, saturation, failure injection, and recovery; record commands, topology, distributions, errors, duplicates/loss, and recovery evidence.
- [ ] 7.3 Run canonical `/mcp` public canaries and a real rendered chatbot conversation in which a newborn Tier-1 user sees current terms, explicitly accepts them, activates the exact universe, and completes remote `converse` without maintainer quota or a desktop; record prompt/result plus trace or screenshot.
- [ ] 7.4 Verify post-fix clean user use through privacy-reviewed production evidence; if none exists, leave a dated STATUS watch item rather than claiming proof.
- [ ] 7.5 Obtain explicit rollout approval, remove isolated test registrations, and cut over only after rollback preserves signed/financial evidence, monotonic fences, and held assignments without reinterpreting legacy state.

## 8. Foldback

- [ ] 8.1 Re-run strict OpenSpec, focused/full tests, lint, security, concurrency/load, public canary, rendered-chatbot, and independent exact-diff review at the landing SHA.
- [ ] 8.2 Sync the four deltas into canonical specs and archive this change only after implementation and production-shaped acceptance are complete.
- [ ] 8.3 Delete the landed STATUS implementation row, retire the worktree lane, and publish final authority, evidence, rollback, and post-fix-use records.
