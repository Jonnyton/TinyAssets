## Premise verification — 2026-07-24

Compared against `origin/main`, unlanded
`codex/osx-paid-market-transport`, and the 30 open PRs requested by the lane.
`live` means independently buildable while dark; `blocked-*` work stays
unchecked.

| Task | Classification | Evidence / boundary |
|---|---|---|
| 1.3 | built | Wave 2 is unlanded at 15/37; wallet/chain, R2-1 receipts, S14/B36, tenant, and domain owners are not live. |
| 2.1 | blocked-domain-owner | Draft PR #1679 owns the amended descriptor grammar and requires opposite-provider re-review before 2.1/2.2. |
| 2.2 | blocked-domain-owner | Same #1679 gate; do not implement its moving descriptor/market-class contract here. |
| 2.3 | built | Opaque descriptor ids, injected issuer verification, exact canonical bytes, mutation refusal, recomputed totals, and conserved pure capacity values are covered. Atomic persistence remains in 5.1. |
| 2.4 | built | Exact landed-total and quote validation is pure and transport-independent. |
| 2.5 | blocked-domain-owner (standalone subset built) | Quote-field mutation coverage is built; facet/substitutability coverage waits for #1679. |
| 3.1 | built | Fail-closed observation joins and independently fresh price fields use fixture receipts only. |
| 3.2 | built | The field-fresh oracle is differential-tested against landed canonical settlement/index primitives. |
| 3.3 | built | The credential-blind read-only protocol cannot execute or return an executable route. |
| 3.4 | built | Two fake adapters cover complete, partial, malformed, stale, timeout, and independent-failure cases without live calls. |
| 3.5 | stale-inverted → built | Account- and principal-root self-trades stay excluded while every positive-gross settlement retains the canonical fee. Pair/buyer/seller-root dampening, infeasible-cap equal weighting, and composite-only clamping are covered. |
| 4.1 | built | Explicit free/BYOC/paid mandate selection creates no provider or money effect. |
| 4.2 | built | Pure eligibility/ranking returns evidence only and owns no reservation. |
| 4.3 | blocked-tenant (standalone value built) | Immutable receipt, ACL, retention, replay, and projection policy is built; durable tenant storage remains gated. |
| 4.4 | built | Boundary/mutation tests prove the result grants no execution, credential, capacity, or money authority. |
| 5.1 | blocked-transport-landing | Requires Wave 2 workflow/CAS plus tenant, domain capacity, and S14/B36 owners. |
| 5.2 | blocked-transport-landing | Also blocked on wallet/chain receipts, domain acceptance, tenant authority, and host cutover. |
| 5.3 | built | Pure dark order policy composes the landed bucket and settlement oracles; no durable lock or transport was added. |
| 5.4 | built | Pure allow/refuse policy keeps unsupported instruments dark without registration. |
| 5.5 | blocked-host/legal (standalone gate built) | Missing, stale, mismatched, automated, or incomplete review stays dark; no current specialist artifact exists. |
| 6.1 | blocked-boundary | Public reads require tenant/privacy, boundary, load/security, canary, chatbot, and host activation gates. |
| 6.2 | blocked-tenant | Full handoff proof also needs R2-1, Wave 2, domain capacity, and boundary owners. |
| 6.3 | blocked-S14/B36 | Requires landed transport/public surfaces, tenant owner, and a reviewed capacity harness; draft PR #1695 is planning-only. |
| 6.4 | blocked-S14/B36 | Depends on 6.3 environment evidence and independent security/concurrency review. |
| 6.5 | blocked-host | No advertisement, live rollout, canary, chatbot proof, or organic-use evidence is authorized. |
| 7.1 | built | Refusal/default-dark definitions are explicit and no workflow, deployment registration, migration, or feature enablement was added. |
| 7.2 | blocked-transport-landing | Sync/archive would falsely claim the blocked public, executable, load, legal, and rollout work is complete. |

## 1. Contract ownership and review gates

- [x] 1.1 Release `paid-market-price-index-and-forwards` from the Wave 2 transaction/migration change and record this change as the build-forward umbrella’s narrow live-price successor.
- [x] 1.2 Obtain opposite-provider review of the proposal, design, full delta, and compute/LLM/task/fabrication research now archived by PR #1648 against TinyAssets context. Claude Sonnet approved the corrected source mapping on 2026-07-22; the verdict is recorded in `docs/audits/2026-07-22-paid-market-live-price-source-review.md`.
- [x] 1.3 Confirm the Wave 2 logical-accounting transaction owner, required wallet/chain-effect successor from `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6, outbound boundary authority/receipts successor, tenant identity/isolation, R2-1 provider authority/credential-class receipts, distributed execution, and each domain capacity/evidence owner have landed before their dependent adapter, public, executable, settlement, or paid-observation tasks; otherwise keep those tasks blocked and dark. Premise audit above records every dependent task and leaves all gated behavior dark.
- [x] 1.4 Run `openspec validate paid-market-live-price-discovery --strict`, full strict validation, requirement/scenario counts, and `git diff --check` after every contract amendment.
- [x] 1.5 (done 2026-07-25: Claude Opus 5 round-1 ADAPT -> six adaptations folded -> round-2 APPROVE; verdict held by the fable-fleet lead session and summarized in the PR #1679 comment thread) Obtain opposite-provider re-review of the amended V1 descriptor grammar, one-profile supply identity, four closed lane schemas, schema-owned comparison direction, separately derived public market-class identity, observation-scope provenance, demand/private-scope separation, error privacy, and digest contracts before starting tasks 2.1 or 2.2.

## 2. Pure descriptors, quotes, and evaluation

- [ ] 2.1 Add failing unit/property tests for the exact bounded ASCII canonical grammar; normalized structured construction versus strict canonical-byte verification; deterministic error precedence and safe paths; golden domain-separated descriptor and market-class `sha256:` identities; one atomic correlated and independently supportable supply profile per descriptor; all four closed lane schemas; immutable validator-revision attestation; schema-owned range and required-set-subset comparison; unsupported versions/revisions; overlapping compatible supply mapping to one normalized public market class; extra supply headroom not changing that class; demand/private values staying outside public identity; quote-bound observation-scope provenance; and hard substitutability mismatches.
- [ ] 2.2 Implement pure immutable descriptor and public market-class projection values outside provider/domain execution code with an explicitly injected per-call validator that attests one immutable profile-schema revision and no mutable registry; derive rather than accept both ids; keep private demand commitments tenant-keyed and keep payloads, credentials, prices, routing, reservation, and execution absent.
- [x] 2.3 Add failing tests for indicative versus native firm authority; versioned domain-separated canonical bytes; unknown-field refusal; server-recomputed totals; complete signed-field coverage; enrolled/revoked issuer keys; tenant/demand/descriptor/terms/fee/nonce/expiry/offer binding; and conserved single/partial capacity consumption.
- [x] 2.4 Implement pure deterministic quote validation and landed monetary normalization for inference, training, task, and fabrication with one settlement currency, exact canonical fee version, priced-component coverage, explicit service attributes/objective weights, optional separately approved FX binding, and exact integer/rational arithmetic.
- [ ] 2.5 Add mutation/property tests proving nominal unit price, stale fields, unsupported facets, or a changed descriptor cannot alter eligibility or silently substitute supply.

## 3. Price surfaces and reference adapters

- [x] 3.1 Add failing tests for per-descriptor raw-VWAP/native-ask/external-ceiling/composite-index fields, independent timestamps/TTLs/sample counts/owner counts, null versus zero, valid all-in ceiling clamp-and-flag, incomplete/stale never-clamp behavior, confidence flags, and fail-closed paid-observation joins across tenant/universe identity, fence-bound accepted-result identity, parties, currency/token/chain, gross/net/fee amounts, and the finality/reorg status defined by `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6.
- [x] 3.2 Implement the pure field-fresh aggregation oracle and differential-test it against canonical paid-market settlement/index primitives.
- [x] 3.3 Define the read-only credential-blind reference-adapter boundary and add contract tests proving it cannot execute, reserve, claim, settle, access secrets, or return an executable route.
- [x] 3.4 Add at least two fake external reference adapters and fault tests for timeout, malformed units/currency, incompatible terms, omitted tax/egress/region/minimum/discount components, partial staleness, independent failure, and partial-reference labeling; use no live credential, quota, or paid API.
- [x] 3.5 Add economic-principal-root manipulation tests for split offers, counterparties, workforce/OAuth/seller accounts, reversed pair direction, unknown linkage, exact same-owner ingestion exclusion without a settlement-fee waiver, recorded canonical fees for every positive-gross settlement including linked-party trades, concentration caps, raw-native-price immutability, composite-only ceiling clamp behavior, and low-confidence thin markets.

## 4. Deterministic economic routing

- [x] 4.1 Add failing tests proving the requester chooses free, BYOC, or paid fulfillment and that unavailable free/BYOC work never creates a paid lock or maintainer/provider call.
- [x] 4.2 Implement pure verified-eligibility/hard-constraint filtering and versioned landed-monetary ranking with stable tie-breaks, explicit service-attribute handling, single-currency/FX rules, complete rejection reasons, cap/fee-version enforcement, and no capacity or money reservation side effect.
- [ ] 4.3 Add tenant-private reproducible evaluation receipts with opaque tenant-keyed commitments, owner/admin/auditor ACLs, non-enumerable ids, candidate versions/freshness, reason codes, monetary/service breakdown, retention/hold/deletion/export policy, and aggregate-only public projection.
- [x] 4.4 Mutation-test that quote ranking cannot authorize provider credentials, alter provider fallback chains, skip domain-native execution fences, or treat ranking as reservation/acceptance/invoice/settlement.

## 5. Native firm capacity and forwards

- [ ] 5.1 After prerequisites land, add failing integration tests for signed short-lived native firm quotes, domain-created tenant/demand/quote/descriptor/quantity/expiry/fence capacity grants, one atomic consumption winner, partial-consumption conservation, offer-version CAS, expiry/cancellation, and no double-sell under response loss.
- [ ] 5.2 Implement native firm-quote publication and the default-off selection handoff only: the domain owner creates/fences capacity, `paid-market-economy` records logical budget reservation/accounting intent, and the successor defined by `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6 owns wallet/chain effects; discovery evaluates and revalidates but creates none of those authorities. Require that successor's matching verified receipt before a paid settlement becomes a price observation. Add no external-provider execution.
- [x] 5.3 Add failing forward tests for exact 8-hour/day/week buckets, ≤28-day horizon, 1M/10M/100M sizes, batch-only initial class, immutable id, authenticated monotone lifecycle, collateral-before-executable, spot collateral-free, deterministic best ask, exact pro-rata demand-relative settlement, threshold-only slashing, buyer compensation, and no-show behavior.
- [x] 5.4 Implement only physically delivered native spot/forward instruments; reject cash settlement, secondary transfer, leverage/netting, proprietary-model resale, and F3 swarm execution.
- [ ] 5.5 Before any forward, training, or hardware route is advertised or enabled in a jurisdiction, obtain and bind a current specialist legal-review artifact covering the CFTC facts-and-circumstances forward-contract-exclusion test, applicable commodities/derivatives/securities/consumer/money-transmission rules, and the narrower knowledge-based BIS/export-control triggers; add `tests/test_paid_market_jurisdiction_gates.py` proving missing/stale review keeps the route dark and no automated label is presented as legal approval.

## 6. Public, security, concurrency, and uptime proof

- [ ] 6.1 Add unauthenticated CDN-cacheable aggregate quote/model/curve-equivalent reads with 60-second TTL, explicit limits, and primary-text units, currency, landed total, component coverage, executability, freshness, source class, confidence, and caveats; revalidate tenant/issuer/eligibility/fee/offer/capacity authority outside the cache before handoff.
- [ ] 6.2 Run authorization/privacy tests proving composite tenant keys on private quote/receipt/cache/capacity/idempotency/settlement handoffs; cross-tenant non-enumerability; revocation-invalidated caches; provider contract/subprocessor/locality/retention/attestation eligibility; no credential/payload leakage; no ambient maintainer authority; and no executable route without BYOC or an accepted market lease.
- [ ] 6.3 Run capability-sharded load tests for at least 200 concurrent ranking refreshes, 500 daemon offers, 1,000 requests over five minutes, adapter failures, hot-class reads, tenant fairness, and bounded no-host behavior with no poll-all loop.
- [ ] 6.4 Record environment, exact commands, p50/p95/p99, cache hit/staleness, CPU/pool occupancy, failure counts, duplicate locks, and starvation/leakage results; obtain independent security/concurrency/diff review.
- [ ] 6.5 Before advertisement, pass live canaries and a real rendered chatbot quote conversation; after rollout, record freshness-stamped organic clean-user evidence or leave a STATUS watch item.

## 7. Foldback

- [x] 7.1 Keep external execution/BYOK resale, proprietary instruments, F3 swarm, cash/secondary instruments, and automatic paid fallback explicitly dark in code, docs, and deployment configuration.
- [ ] 7.2 Sync the implemented requirements into canonical `paid-market-price-index-and-forwards`, validate idempotently, archive the change, and retire its STATUS row in the landing commit.
