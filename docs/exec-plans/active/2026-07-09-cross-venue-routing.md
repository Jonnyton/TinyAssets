# Cross-Venue Routing — Switzerland, Literally (2026-07-09)

**Status:** Binding design note. The neutrality thesis at full extension: TinyAssets connects to ALL compute markets and owns no layer — including the market layer.

## 1. External venues are ledger connections
Hosted APIs, GPU-hour marketplaces (Vast/Akash-class), other decentralized venues — each attaches to the user's resource ledger as a CONNECTION via boundary-layer adapters (adapters-as-commons, auth-injection hard rule applies). The universe routes each job to the cheapest ADEQUATE source anywhere: own hardware -> subscriptions -> own keys -> native market -> external venues — under the user's caps, always.

## 2. The reference generalizes
Top-line reference := the cheapest adequate route that is currently executable
over the Internet under the requester's credentials, caps, and policy (not a
stale, theoretical, or inaccessible quote). Native and connected supply then
compete below that reference through supply and demand. The native market must
beat the executable world reference to win a job. This is what "leaning into
commoditization" means operationally: the platform profits from compute getting
cheaper anywhere, because routing flow and data value grow while margin owners
bleed.

## 3. Cross-venue index — the Bloomberg of all compute (day-one value)
The market-data layer aggregates every connected venue's prices into one index — valuable before the native venue has a single trade (extends the "price index first" bootstrap to the whole industry).
**Unit normalization (honest hard part):** GPU-hour venues and token venues price different things. Conversion runs through throughput benchmarks per (model, hardware class) — produced by existing capability benchmarking, held in the commons — publishing $/Mtok equivalents flagged `estimate: true` with the benchmark provenance. **Venue trust classes** annotate differing verification/SLA regimes; never present venues as equivalent when their guarantees differ.

## 4. Fee posture (credibility test — HARD RULE)
**Every TinyAssets settlement pays the canonical fee, regardless of whether
the selected supply is native, connected, external, or same-owner.** A
read-only route comparison or a direct use of the requester's own external
account that creates no TinyAssets settlement has no settlement fee because no
settlement occurred; it is not a fee exemption. The native venue wins through
adequacy and supply/demand competition below the executable Internet
reference, never through a hidden route preference. "We don't own any layer,
including the market layer" must be verifiable, not trusted.

## 5. Best execution generalizes
Smart order routing across venues: the match/best-execution discipline extends conceptually from offers-within-a-bucket to sources-across-venues (adequacy gates first, then cost, deterministic tie-breaks, estimates flagged). Adequacy is the user's own gates — a cheaper venue that fails quality gates is not cheaper.

## 6. Sequencing
Cross-venue price aggregation ships WITH the native index (it is the same read layer, more sources). Routing adapters follow demand: seed hosted-API + one GPU-hour venue adapter; the commons builds the rest (bounties for venue adapters are ideal seed bounties).
