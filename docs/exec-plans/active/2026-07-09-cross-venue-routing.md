# Cross-Venue Routing — Switzerland, Literally (2026-07-09)

**Status:** Binding design note. The neutrality thesis at full extension: TinyAssets connects to ALL compute markets and owns no layer — including the market layer.

## 1. External venues are ledger connections
Hosted APIs, GPU-hour marketplaces (Vast/Akash-class), other decentralized venues — each attaches to the user's resource ledger as a CONNECTION via boundary-layer adapters (adapters-as-commons, auth-injection hard rule applies). The universe routes each job to the cheapest ADEQUATE source anywhere: own hardware -> subscriptions -> own keys -> native market -> external venues — under the user's caps, always.

## 2. The ceiling generalizes
Ceiling := best external price across ALL connected venues (not just hosted APIs). The native market must beat the world to win a job. This is what "leaning into commoditization" means operationally: the platform PROFITS from compute getting cheaper anywhere, because routing flow and data value grow while margin-owners bleed.

## 3. Cross-venue index — the Bloomberg of all compute (day-one value)
The market-data layer aggregates every connected venue's prices into one index — valuable before the native venue has a single trade (extends the "price index first" bootstrap to the whole industry).
**Unit normalization (honest hard part):** GPU-hour venues and token venues price different things. Conversion runs through throughput benchmarks per (model, hardware class) — produced by existing capability benchmarking, held in the commons — publishing $/Mtok equivalents flagged `estimate: true` with the benchmark provenance. **Venue trust classes** annotate differing verification/SLA regimes; never present venues as equivalent when their guarantees differ.

## 4. Fee posture (credibility test — HARD RULE)
**No fee on external pass-through.** The 1% applies only where OUR settlement adds value (escrow, verification, gates). Routing through a user's own external account costs nothing, exactly like their own API keys. The native venue wins on integration (volunteer lane, gates, gardeners, forecastable demand) — never on lock-in or toll-booth routing. "We don't own any layer, including the market layer" must be verifiable, not trusted.

## 5. Best execution generalizes
Smart order routing across venues: the match/best-execution discipline extends conceptually from offers-within-a-bucket to sources-across-venues (adequacy gates first, then cost, deterministic tie-breaks, estimates flagged). Adequacy is the user's own gates — a cheaper venue that fails quality gates is not cheaper.

## 6. Sequencing
Cross-venue price aggregation ships WITH the native index (it is the same read layer, more sources). Routing adapters follow demand: seed hosted-API + one GPU-hour venue adapter; the commons builds the rest (bounties for venue adapters are ideal seed bounties).
