## 1. Contract ownership and review gates

- [x] 1.1 Release `paid-market-price-index-and-forwards` from the Wave 2 transaction/migration change and record this change as the build-forward umbrella’s narrow live-price successor.
- [ ] 1.2 Obtain opposite-provider review of the proposal, design, full delta, PR #1574 sources, and TinyAssets context; resolve every blocking finding before implementation.
- [ ] 1.3 Confirm the Wave 2 logical-accounting transaction owner, required §18.6 wallet/chain-effect successor, outbound boundary authority/receipts successor, tenant identity/isolation, R2-1 provider authority/credential-class receipts, distributed execution, and each domain capacity/evidence owner have landed before their dependent adapter, public, executable, settlement, or paid-observation tasks; otherwise keep those tasks blocked and dark.
- [x] 1.4 Run `openspec validate paid-market-live-price-discovery --strict`, full strict validation, requirement/scenario counts, and `git diff --check` after every contract amendment.

## 2. Pure descriptors, quotes, and evaluation

- [ ] 2.1 Add failing unit/property tests for stable versioned capability descriptors, canonical digest stability, exact lane facets, unsupported versions, demand-specific values staying in `DemandIntent`, range/set compatibility, resolved-term binding, and hard substitutability mismatches.
- [ ] 2.2 Implement pure immutable descriptor and quote values outside provider/domain execution code; keep domain facet validators injected and keep private payloads/credentials absent.
- [ ] 2.3 Add failing tests for indicative versus native firm authority; versioned domain-separated canonical bytes; unknown-field refusal; server-recomputed totals; complete signed-field coverage; enrolled/revoked issuer keys; tenant/demand/descriptor/terms/fee/nonce/expiry/offer binding; and conserved single/partial capacity consumption.
- [ ] 2.4 Implement pure deterministic quote validation and landed monetary normalization for inference, training, task, and fabrication with one settlement currency, exact canonical fee version, priced-component coverage, explicit service attributes/objective weights, optional separately approved FX binding, and exact integer/rational arithmetic.
- [ ] 2.5 Add mutation/property tests proving nominal unit price, stale fields, unsupported facets, or a changed descriptor cannot alter eligibility or silently substitute supply.

## 3. Price surfaces and reference adapters

- [ ] 3.1 Add failing tests for per-descriptor raw-VWAP/native-ask/external-ceiling/composite-index fields, independent timestamps/TTLs/sample counts/owner counts, null versus zero, valid all-in ceiling clamp-and-flag, incomplete/stale never-clamp behavior, and confidence flags.
- [ ] 3.2 Implement the pure field-fresh aggregation oracle and differential-test it against canonical paid-market settlement/index primitives.
- [ ] 3.3 Define the read-only credential-blind reference-adapter boundary and add contract tests proving it cannot execute, reserve, claim, settle, access secrets, or return an executable route.
- [ ] 3.4 Add at least two fake external reference adapters and fault tests for timeout, malformed units/currency, incompatible terms, omitted tax/egress/region/minimum/discount components, partial staleness, independent failure, and partial-reference labeling; use no live credential, quota, or paid API.
- [ ] 3.5 Add economic-principal-root manipulation tests for split offers, counterparties, workforce/OAuth/seller accounts, reversed pair direction, unknown linkage, transaction-owned exact same-owner `self_hosted_zero_fee` ingestion/exclusion, recorded ordinary fees for non-exempt linked-party paid trades, concentration caps, raw-native-price immutability, composite-only ceiling clamp behavior, and low-confidence thin markets.

## 4. Deterministic economic routing

- [ ] 4.1 Add failing tests proving the requester chooses free, BYOC, or paid fulfillment and that unavailable free/BYOC work never creates a paid lock or maintainer/provider call.
- [ ] 4.2 Implement pure verified-eligibility/hard-constraint filtering and versioned landed-monetary ranking with stable tie-breaks, explicit service-attribute handling, single-currency/FX rules, complete rejection reasons, cap/fee-version enforcement, and no capacity or money reservation side effect.
- [ ] 4.3 Add tenant-private reproducible evaluation receipts with opaque tenant-keyed commitments, owner/admin/auditor ACLs, non-enumerable ids, candidate versions/freshness, reason codes, monetary/service breakdown, retention/hold/deletion/export policy, and aggregate-only public projection.
- [ ] 4.4 Mutation-test that quote ranking cannot authorize provider credentials, alter provider fallback chains, skip domain-native execution fences, or treat ranking as reservation/acceptance/invoice/settlement.

## 5. Native firm capacity and forwards

- [ ] 5.1 After prerequisites land, add failing integration tests for signed short-lived native firm quotes, domain-created tenant/demand/quote/descriptor/quantity/expiry/fence capacity grants, one atomic consumption winner, partial-consumption conservation, offer-version CAS, expiry/cancellation, and no double-sell under response loss.
- [ ] 5.2 Implement native firm-quote publication and the default-off selection handoff only: the domain owner creates/fences capacity, `paid-market-economy` records logical budget reservation/accounting intent, and the required §18.6 successor owns wallet/chain effects; discovery evaluates and revalidates but creates none of those authorities. Require the matching verified §18.6 receipt before a paid settlement becomes a price observation. Add no external-provider execution.
- [ ] 5.3 Add failing forward tests for exact 8-hour/day/week buckets, ≤28-day horizon, 1M/10M/100M sizes, batch-only initial class, immutable id, authenticated monotone lifecycle, collateral-before-executable, spot collateral-free, deterministic best ask, exact pro-rata demand-relative settlement, threshold-only slashing, buyer compensation, and no-show behavior.
- [ ] 5.4 Implement only physically delivered native spot/forward instruments; reject cash settlement, secondary transfer, leverage/netting, proprietary-model resale, and F3 swarm execution.

## 6. Public, security, concurrency, and uptime proof

- [ ] 6.1 Add unauthenticated CDN-cacheable aggregate quote/model/curve-equivalent reads with 60-second TTL, explicit limits, and primary-text units, currency, landed total, component coverage, executability, freshness, source class, confidence, and caveats; revalidate tenant/issuer/eligibility/fee/offer/capacity authority outside the cache before handoff.
- [ ] 6.2 Run authorization/privacy tests proving composite tenant keys on private quote/receipt/cache/capacity/idempotency/settlement handoffs; cross-tenant non-enumerability; revocation-invalidated caches; provider contract/subprocessor/locality/retention/attestation eligibility; no credential/payload leakage; no ambient maintainer authority; and no executable route without BYOC or an accepted market lease.
- [ ] 6.3 Run capability-sharded load tests for at least 200 concurrent ranking refreshes, 500 daemon offers, 1,000 requests over five minutes, adapter failures, hot-class reads, tenant fairness, and bounded no-host behavior with no poll-all loop.
- [ ] 6.4 Record environment, exact commands, p50/p95/p99, cache hit/staleness, CPU/pool occupancy, failure counts, duplicate locks, and starvation/leakage results; obtain independent security/concurrency/diff review.
- [ ] 6.5 Before advertisement, pass live canaries and a real rendered chatbot quote conversation; after rollout, record freshness-stamped organic clean-user evidence or leave a STATUS watch item.

## 7. Foldback

- [ ] 7.1 Keep external execution/BYOK resale, proprietary instruments, F3 swarm, cash/secondary instruments, and automatic paid fallback explicitly dark in code, docs, and deployment configuration.
- [ ] 7.2 Sync the implemented requirements into canonical `paid-market-price-index-and-forwards`, validate idempotently, archive the change, and retire its STATUS row in the landing commit.
