# Track H — Pooled Training & Fractional Model Ownership

**Date:** 2026-07-08
**Author:** founder + Claude (design session)
**Status:** Dispatch-ready design spec. Exactness-critical math implemented and tested (`tinyassets/paid_market/pool.py`: pool funding, largest-remainder revenue apportionment, attribution-chain splits — 111-test suite total, conservation sweeps included).
**Composes:** Track E (escrow, price index), Track F (training instruments, checkpoint settlement, capability minting), plus two primitives **already in the codebase**: `goal_pool/` and the attribution chain (`record_remix` / `get_provenance` in `api/market.py`).

---

## 0. The gap this closes

An individual affords an F1 fine-tune; nobody affords an F2 pretraining window alone. Democratizing pretraining therefore means democratizing **capital**: many users fund one training goal, the run pays from the pool, and the minted model is owned fractionally by its funders — with revenue flowing back automatically when the model earns on the inference market. No other platform has goal pools, attribution provenance, outcome gates, and a compute market adjacent to each other; Track H is pure composition of owned primitives.

## 1. Lifecycle

```
goal (train model M to gate ladder L)
  → pool opens (target = quoted F1/F2 cost + verification overhead)
  → contributions accrue in escrow           [pool.py: settle_pool_funding]
       filled  → funds committed to a Track F instrument
       expired → exact full refund, pool closes
  → training runs; checkpoints settle per Track F
       run FAILS terminally → unspent escrow refunded pro-rata to
       accepted contributions [apportion_exact]; spent portion is gone
       (funders bear run risk — stated in the pool terms, not hidden)
  → gates claimed with eval evidence (staged release optional per gate)
  → capability minted (Track F §5) with OWNERSHIP TABLE attached:
       owner_shares = accepted contributions, verbatim
       attribution_ppm + attribution_shares frozen at mint from the
       remix/provenance records of the base model
  → model earns on the inference market
  → every revenue event splits: attribution_ppm up the lineage first,
    remainder to owners — both legs exact  [distribute_revenue]
```

## 2. The math that must not drift (implemented)

**Funding close** (`settle_pool_funding`): contributions processed in arrival order (order is consensus-critical — persist it); the crossing contribution splits exactly (accepted part + refunded overshoot); late contributions refunded whole; failed pool refunds everything. Per-contributor conservation asserted: accepted + refunded == paid, always.

**Revenue apportionment** (`apportion_exact`): naive floor pro-rata leaks up to n−1 micros per distribution — dust that compounds across thousands of payout events into real missing money and unbalanceable ledgers. Largest-remainder apportionment guarantees `sum(payouts) == revenue` exactly, every owner within 1 micro of exact pro-rata, deterministic tie-break (remainder desc, key asc) so every node computes identical payouts.

**Attribution split** (`distribute_revenue`): `attribution_ppm` of each revenue event flows to the lineage owners *first*, remainder to the model's owners; both legs apportion exactly and jointly conserve. The rate is frozen at mint from remix records — derived models pay their base forever, which makes releasing a model *into* the commons an investment rather than a donation. This is the economic engine that makes open weights self-sustaining.

## 3. Ownership semantics (deliberately minimal in v1)

Shares are the accepted-contribution integers, immutable at mint. **No secondary transfer of shares in v1** — transferable fractional model shares walk straight into securities-law territory across most jurisdictions; that is a legal-review gate, not an engineering task, and the spec names it so nobody ships it casually. What v1 owners get: revenue distribution, governance-lite (owners vote to re-license or open-weight the model via existing gate/consultation machinery), and provenance credit.

## 4. Attribution rates

Default `attribution_ppm` at mint: 0 for models trained from scratch; for derived models, set from the base's declared remix terms (recorded via `record_remix` at training time). Chains compose: a remix-of-a-remix pays its immediate base, whose own distribution pays *its* base — depth handled by each model's own frozen table, so no unbounded recursion in any single revenue event.

## 5. Risk surface (named honestly)

- **Run failure:** funders lose the spent portion — pool terms state this on the tin. Checkpoint settlement (Track F) minimizes the blast radius; gates can stage escrow release so unspent tranches survive a failed run.
- **Valuation:** pools fund *cost*, not *worth*. The pool fills at the quoted training price; whether the model earns anything is the funders' bet. The platform quotes costs (Track E index), never returns.
- **Sybil pooling:** shares proportional to money in — sybils gain nothing (splitting a contribution across wallets splits the payout identically).
- **Regulatory:** see §3. Revenue-bearing fractional ownership is the closest thing in the whole stack to a security; v1's non-transferability is the conservative posture pending counsel.

## 6. Waves

| Wave | Ships | Depends on |
|---|---|---|
| H-W1 | Pool CRUD on `goal_pool/`, escrowed funding, exact close/refund | Track E W2 escrow |
| H-W2 | Mint with ownership table; revenue distribution wired to inference settlements | Track F W1 minting |
| H-W3 | Attribution-chain payments from remix records; owner governance-lite | H-W2 |

## 7. Out of scope

Share transfer/secondary market (legal gate); model valuation or return projections; DAO tooling; cross-model index funds; lending against shares.
