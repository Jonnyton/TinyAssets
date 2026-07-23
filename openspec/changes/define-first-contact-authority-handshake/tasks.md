> **Review-blocked planning change.** Tasks 2.1-6.6 MUST NOT begin until task
> 1.2 has an accepted opposite-provider verdict. No task may use project
> maintainer/founder/operator keys, subscriptions, quota, hardware, accounts,
> live funds, or hidden platform compute.

## 1. Contract and independent review

- [ ] 1.1 Strictly validate this proposal, design, identity/access-control delta, and credential-vault delta against all current specs and active changes.
- [ ] 1.2 After Claude capacity resets, obtain an independent primary-source and TinyAssets security review with verdict `approve` or `adapt`; incorporate every required adaptation and re-review to acceptance before runtime work.
- [ ] 1.3 Confirm draft PR #1606 has landed and its live migration/canary proves the persistent engine ceiling and provider isolation prerequisite without maintainer-quota use.
- [ ] 1.4 Confirm R2-1b has landed one race-safe provider result/receipt object for both universe-intelligence writer calls; extend it rather than creating a parallel receipt or process-global provider state.
- [ ] 1.5 After draft PR #1606 and current owners clear, reconcile `universe-creation` by replacing its overlapping authority tasks 2.1-4.7 with dependencies/references to this integration contract while retaining its lifecycle/migration/final-acceptance tasks; broaden the `STATUS.md` write claim before editing it.
- [ ] 1.6 Split implementation into narrow worktree slices with exact `STATUS.md` file claims after accepted review; market ranking/acceptance/reservation, training-group formation, and settlement remain in paid-market/distributed-execution successors.

## 2. Authority and delegation contract tests

- [ ] 2.1 Add fake-only tests for server-issued request identity, exact request/operation digest, principal/universe/domain-separated stable invocation ids without cross-tenant collision, requester/client/universe audiences, issued/not-before/expiry with bounded skew, policy digest, phase requirements, and workload-specific completeness.
- [ ] 2.2 Add tests proving universe ACL membership and founder/admin/platform roles do not confer spending authority, while an explicit narrow self/organization delegation admits only its subject, universe, phase, provider/model, budget, and validity scope.
- [ ] 2.3 Add expiry, revocation, and policy race tests proving every invocation revalidates current facts; a sealed authority is replaced rather than mutated, while its stable invocation id preserves consumed/unknown spend state across re-resolution.
- [ ] 2.4 Implement the immutable authority and requester-owned grant types plus a resolver that returns typed success/partial/held results without invoking a provider.

## 3. Secretless setup and requester-owned authority

- [ ] 3.1 Add tests proving held first contact returns non-secret, short-lived, single-use, requester/universe-bound setup descriptors and never asks for or echoes a raw credential in chat, canonical-handle input, logs, traces, outcomes, or receipts.
- [ ] 3.2 Add cross-principal, access-revoked, replay, expiry, and retry tests for setup challenges; completion rechecks current tenant/universe/delegation/custody ownership, a challenge is not authority, and enrollment requires fresh request resolution.
- [ ] 3.3 Replace any public raw-key intake path with a same-origin HTTPS out-of-band vault/provider authorization flow with exact redirects, CSRF state, PKCE, encrypted KMS/secret-manager custody, and its own auth/UI review; retain seven handles and never reuse the MCP token upstream.
- [ ] 3.4 Resolve requester-owned vault/device/broker references into verified non-secret grants; vend only scoped ephemeral leases, destroy them after use, and reject plaintext/base64 custody or secret exposure to authority/results.
- [ ] 3.5 Coordinate with distributed/external-effect owners and migrate every `resolve_github_token` consumer (`auto_ship_pr`, GitHub PR effectors, and discovered callers) to owner/destination/purpose/route/job/expiry-scoped broker leases; test mismatch, custody failure, cleanup, and no ambient fallback before retiring the resolver.

## 4. Market mandate, agreement, and routing boundary

- [ ] 4.1 Add fake-only authority-admission tests for already-issued purchase mandates, including exact capability/model/interface/phase, venues/providers, privacy/compliance/locality/license, integer price limits, currency, validity, and bounded actor delegation.
- [ ] 4.2 Add authority-admission tests for already-reserved exact agreements, including mandate/accepting-actor proof, capacity, price/fees/unit basis, allocation/escrow, M1/M3 authority, M2 binding only, fresh predicate evidence, validity, sender binding, and fence.
- [ ] 4.3 Add replay/supersession/fence tests proving stale, duplicate, unreserved, or no-longer-current agreements cannot be admitted; the paid-market owner remains responsible for compare-and-set acceptance/reservation.
- [ ] 4.4 Implement a read-only mandate/agreement verifier that consumes the reviewed paid-market/distributed-execution records without ranking offers, accepting/reserving capacity, forming groups, or settling.
- [ ] 4.5 Verify every mandate/agreement/compute-model/evidence/privacy/price incompatibility returns a hold; cheapest-adequate ranking and exact agreement creation remain outside this change.
- [ ] 4.6 Add authority-admission tests proving pre-agreement discovery content is never consumed and an already-formed canonical training group is admitted only when full membership/window/fence/allocation evidence is current; do not form the group here.

## 5. Provider intersection, phases, receipts, and isolation

- [ ] 5.1 Add tests proving effective authority is the intersection of persistent engine ceiling, request grants, exact market agreements, phase requirements, current policy/privacy, and current lease fence; every boundary only narrows.
- [ ] 5.2 Thread the authority through reply generation and learning extraction so each receives a least-privilege phase view and a covered reply plus uncovered extraction returns a typed partial result.
- [ ] 5.3 Extend graph execution to resolve declared node/phase authority per run rather than reusing chat authority indefinitely; preserve existing distributed-execution lease/fence semantics.
- [ ] 5.4 Extend the R2-1b result object and persistence with stable-invocation-keyed, endpoint-redacted, idempotent, per-phase receipts including integer usage/unit/currency, quoted and actual all-in charge/fee split, agreement/group-allocation/fence/evidence hashes, policy digest, and terminal or unknown outcome; receipts never release settlement.
- [ ] 5.5 Inventory every adapter's API environment, CLI auth, home/profile/config, cloud chain/metadata, local socket, hardware, in-process client, and market-broker surfaces; unknown surfaces fail closed.
- [ ] 5.6 Add hostile-ambient, cross-daemon/key-substitution, private-endpoint redaction, and isolation-error mutation tests; implement default-deny per-phase overlays and mandatory remote executor proof-of-possession without real provider credentials, subscriptions, quota, hardware, or market funds.

## 6. Verification, rollout, and spec sync

- [ ] 6.1 Run focused auth, delegation, setup, vault, market, routing, phase, receipt, graph, replay, and provider-isolation suites plus repository lint/type checks for touched modules.
- [ ] 6.2 Run the Forever Rule section 14 concurrency/load proof for simultaneous first-contact resolution, exact agreement/group admission, stable invocation/budget dispatch fencing, phase execution, receipt persistence, expiry, and revocation while consuming paid-market-owned reservation evidence.
- [ ] 6.3 Run secret/PII redaction scans over logs, traces, outcomes, receipts, setup flows, and failure artifacts; verify tenant access and retention boundaries.
- [ ] 6.4 Run strict OpenSpec validation, public MCP canaries, and a rendered chatbot `ui-test` covering requester-owned success, market success, setup-required hold, partial extraction, and no-capacity hold.
- [ ] 6.5 Freshness-stamp post-fix real-user evidence that first contact and later phases never consume maintainer resources; leave a short monitoring row if no clean organic use is visible.
- [ ] 6.6 Sync the accepted deltas into canonical specs and archive this change only after implementation, deployment, live proof, and monitoring gates are complete.
