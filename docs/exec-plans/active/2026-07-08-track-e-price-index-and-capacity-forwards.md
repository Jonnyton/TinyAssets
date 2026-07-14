# Track E — Live Price Index + Capacity Forwards (Waves 3–4)

**Date:** 2026-07-08
**Author:** founder + Claude (design session)
**Status:** Dispatch-ready exec plan. Consumes Track A schema, Track E Wave 1 CRUD (`tinyassets/paid_market/`), and assumes Wave 2 (claim + settle + ledger writes) has landed or lands first.
**Foundation classification:** **FOUNDATION** for token-normalized settlement + index computation; **FEATURE** for forward-curve UX.
**Source of truth:**
- Memory: `project_paid_requests_model.md` (requester sets node+LLM+price; daemons filter by LLM, no floor).
- Memory: `project_paid_market_trust_model.md` (cooperative trust; no escrow/rep infra until abuse appears — **partially overridden for forwards, see §6**).
- Spec: `docs/specs/2026-04-18-paid-market-crypto-settlement.md` (state machine, dispute window, escrow `contract.lock` v2 path, 99/1 split).
- Spec: `docs/specs/2026-04-18-full-platform-schema-sketch.md` §1.5b (`capabilities`), §1.6 (`request_inbox`), §1.7 (`ledger`).
- Exec plan: `docs/exec-plans/active/2026-04-20-track-e-paid-market-wave-1.md` (client shape, price-in-cents convention, `_HttpClient` seam, fail-loud per AGENTS.md Hard Rule 8).

**Goal:** a live spot token price and a live forward token price for every open-source LLM traded on the market, quotable from day one at zero volume, hardening into real market prices as flow arrives.

---

## 0. Design summary

Three moves, strictly ordered:

1. **Normalize the unit (Wave 3a).** Settlements currently record `bid_amount` per job. Add token counts so every settled job becomes a price observation in `$/1M tokens` per capability. One-field-class change; everything downstream depends on it.
2. **Composite spot quote (Wave 3b).** Per capability, publish `{last_traded_vwap, best_open_ask, cloud_ceiling}`. Between best ask and ceiling there is always a quotable live number — the index ships before liquidity exists.
3. **Standardized capacity forwards (Wave 4).** Seller-posted, physically-settled, collateralized offers in standard time buckets and standard sizes. The best ask per bucket **is** the live forward price. Cash-settled futures are explicitly out of scope (§7).

Universes consume both feeds as **planning inputs**: redesign a branch for a cheaper model, run on owned hardware, buy spot, or pre-buy a forward window. All adaptation stays in the universe; the market stays dumb (price, match, verify, settle).

---

## 1. Wave 3a — Token-normalized settlement

### Schema (additive migration `006_token_normalization.sql`)

```sql
ALTER TABLE public.request_inbox
  ADD COLUMN tokens_in  bigint,   -- prompt tokens consumed, reported at complete_request
  ADD COLUMN tokens_out bigint;   -- completion tokens produced

ALTER TABLE public.ledger
  ADD COLUMN tokens_in  bigint,
  ADD COLUMN tokens_out bigint,
  ADD COLUMN unit_price_micros_per_mtok bigint;  -- derived at settle: price / (tokens_out/1e6), micros to avoid float
```

File-mode mirror: `settlements/<bid>__<daemon>.yaml` gains `tokens_in`, `tokens_out` (schema_version bump to `"2"`; v1 records remain byte-for-byte untouched per node_bid_conventions.md immutability rule).

### Rules

- `complete_request` RPC requires token counts for `state='completed'`. Missing counts → completion rejected (fail-loud; no silent nulls).
- Daemons report counts from the serving runtime (vLLM/llama.cpp usage stats). **Verification:** counts are cross-checkable against deliverable size heuristics; egregious inflation is a dispute ground within the existing dispute window. No new infra — reuses the moderation backstop.
- Normalization key = `capability_id`. **Capability granularity note:** `node_type:llm_model` does not yet encode quantization / context class / latency class. Acceptable for Wave 3 (prices for the same model at different quants will blend); Wave 5 candidate: widen the capability key. Do NOT block the index on this.

### Tests (~10)

Token counts required on completion; unit-price derivation (micros, integer math); v1 settlement files still parse; ledger rows carry counts; dispute path on count mismatch.

---

## 2. Wave 3b — Composite spot quote

### The quote

Per capability, the published spot quote is three numbers:

| Field | Source | Liveness |
|---|---|---|
| `last_vwap_micros` | Volume-weighted avg of settled `unit_price_micros_per_mtok` over trailing window (default 24h, min 3 settlements; else widen to 7d; else null) | Real trades only |
| `best_ask_micros` | Lowest open standing ask (Wave 4 forwards spilling into current bucket, or Wave 3 seller standing offers if shipped) | Live order state |
| `ceiling_micros` | Cheapest hosted-API price for the same open model, pulled from aggregator feeds (OpenRouter `/models` or equivalent), refreshed hourly, cached | External reference |

**Invariant:** a rational buyer never pays above `ceiling`; the ceiling makes the quote non-null at zero volume. Quote payload includes `as_of` timestamps per field and `n_trades` so consumers can judge staleness — never fabricate liveness.

### Endpoint

`GET /v1/price/{capability_id}` and `GET /v1/prices?model=<llm_model>`.

- **Unauthenticated, cacheable (CDN, 60s TTL), cheap.** This is the single most-hit surface in the system: universes query it during planning, before every market decision. Design budget: p50 < 50ms from cache.
- Also exposed as an MCP tool (`market price` read) so any chatbot-hosted universe can quote it. **MCP contract requirement:** result MUST be in the text content block, not `structuredContent`-only — text-only clients are a known dark-payload failure mode on this connector.

### Index computation

Stdlib-only job in `tinyassets/paid_market/index.py`: recompute per-capability VWAP on each settlement insert (trigger or poll), write to a `price_index` table:

```sql
CREATE TABLE public.price_index (
  capability_id text PRIMARY KEY REFERENCES public.capabilities(capability_id),
  last_vwap_micros bigint,
  vwap_window text NOT NULL,           -- '24h' | '7d'
  n_trades int NOT NULL DEFAULT 0,
  best_ask_micros bigint,
  ceiling_micros bigint,
  updated_at timestamptz NOT NULL DEFAULT now()
);
```

Public-readable RLS (like `capabilities`).

### Manipulation posture (thin-market)

- VWAP over settled trades only (money actually moved + dispute window passed) — wash trading costs the 1% fee both ways, minimum.
- Per-user trade weight cap in the VWAP (a single account's self-dealt volume can't dominate the window) — cheap now, essential before anything ever settles *against* the index.
- Ceiling clamp: index never publishes a VWAP above ceiling (flags it instead).

### Tests (~15)

VWAP math incl. window widening and min-trade floor; per-user weight cap; ceiling fetch failure → stale-but-flagged, never fabricated; MCP text-block presence; cache headers.

---

## 3. Wave 4 — Standardized capacity forwards

### The instrument

A forward = seller's collateralized promise of inference capacity:

> "**{capability_id}**, **{size}** output tokens, deliverable in bucket **{window}**, at **{price_micros_per_mtok}**, collateral **{pct}** locked."

**Standardization is the whole point.** Free-form windows/sizes → incomparable bulletin board. Standard buckets → offers compete directly → best ask per bucket is the live forward price.

- **Time buckets:** 8-hour UTC blocks (00–08 / 08–16 / 16–24), plus calendar-day and calendar-week roll-ups. Sellable up to 28 days ahead.
- **Sizes:** 1M / 10M / 100M output tokens. (Input tokens metered at a fixed published ratio per capability, mirroring hosted-API convention.)
- **Class:** batch only in Wave 4. Interactive-class forwards need uptime SLAs desktops can't honor — deferred.

### Schema (additive `007_forwards.sql`)

```sql
CREATE TABLE public.forwards (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  seller_user_id    uuid NOT NULL,
  daemon_id         text NOT NULL,
  capability_id     text NOT NULL REFERENCES public.capabilities(capability_id),
  bucket_start      timestamptz NOT NULL,      -- must land on standard bucket boundary (CHECK)
  bucket_hours      int NOT NULL CHECK (bucket_hours IN (8, 24, 168)),
  size_mtok         int NOT NULL CHECK (size_mtok IN (1, 10, 100)),
  price_micros_per_mtok bigint NOT NULL,
  collateral_pct    int NOT NULL DEFAULT 20,
  collateral_status text NOT NULL DEFAULT 'none',  -- none|held|released|slashed  (v1 ledger-tracked, v2 contract.lock)
  state             text NOT NULL DEFAULT 'open',
  -- open → sold → delivering → delivered → settled
  --      ↘ expired            ↘ defaulted → slashed+refunded
  buyer_user_id     uuid,
  tokens_requested  bigint NOT NULL DEFAULT 0,  -- buyer demand submitted in-window (B-1)
  tokens_delivered  bigint NOT NULL DEFAULT 0,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX forwards_book ON public.forwards (capability_id, bucket_start, state, price_micros_per_mtok);
```

### Lifecycle (reuses Wave 2 machinery)

1. **Post:** seller posts offer; collateral locked (`ledger` hold in v1; `contract.lock` when the Base escrow path ships — same enum-dispatch seam as settlement modes).
2. **Buy:** buyer pays full price into escrow at purchase (buyer side has no default risk to manage — funds simply sit until delivery, same as spot escrow v2).
3. **Deliver:** during the bucket, buyer's universe submits requests tagged `forward_id`; both `tokens_requested` (demand) and `tokens_delivered` accumulate from Wave 3a token reporting. The seller's obligation is `demand = min(requested, size)` — a capacity reservation, not unilateral token emission (adversarial review finding B-1: measuring against raw size made buyer no-show griefing *profitable*).
4. **Settle:** payment is always pro-rata — buyer is refunded only for *unserved demand* (buyer no-show → seller paid in full, use-it-or-lose-it). The ≥95%-of-demand threshold gates **collateral slashing only**, never rounds payment up (finding A-1). Slash proceeds compensate the buyer, not the treasury (finding B-3). Exact integer math per `tinyassets/paid_market/forwards.py`; conservation invariants asserted at every settlement. Dispute window identical to spot.
5. **Expire:** unsold at bucket start → collateral released, no fee.

**No secondary trading of forwards in Wave 4.** Resale/transfer = out of scope (see §7).

### Forward curve endpoint

`GET /v1/curve/{capability_id}` → per bucket: `{bucket_start, best_ask_micros, open_size_mtok, sold_size_mtok}`. Same caching/MCP posture as the spot quote. The **spot–forward spread** is thereby public: forwards below spot = expected idle supply; above spot = pre-buying ahead of a demand wave — cross-checkable against declared demand in commons branch designs (see §5).

### Tests (~25)

Bucket-boundary CHECKs; book ordering; buy-escrow-deliver-settle happy path; default → pro-rata slash + refund math; expiry release; forward-tagged requests bypass spot pricing; curve endpoint shape; MCP text-block presence.

---

## 4. Buyer caps (spot + forward, uniform)

Already half-present: `max_price_cents` on requests is the per-job price cap. Formalize the pair the platform promises users:

- **`price_cap`** — per capability, max unit price. Enforced at request submission (spot) and purchase (forward).
- **`spend_cap`** — per user per period, total budget across the market tier only (owned compute / own API keys / subscriptions are outside market accounting). Enforced as a ledger check at escrow time. Cap hit → market layer **rejects with a machine-readable reason**; the universe decides what to do (queue, redesign, wait). No substitution logic in the market — per the routing-shape principle, adaptation lives in the universe.

---

## 5. Demand-forecast signal (cheap, high-leverage, optional flag)

Because commons designs carry model requirements, aggregate future demand is visible pre-execution. Publish a coarse daily signal per capability: `n_universes_holding`, `est_tokens_declared` (bucketed, k-anonymized, no universe identifiable). Sellers use it to decide when to post forwards. No other compute market can see demand before it arrives; this is the moat around the forward market. Flag-gated `TINYASSETS_DEMAND_SIGNAL=off` by default pending a privacy pass.

---

## 6. Trust-model amendment (explicit override)

`project_paid_market_trust_model.md` says: cooperative trust, no escrow/rep until abuse appears. **This remains correct for spot** (instant delivery, small stakes, dispute window suffices). **Forwards override it by construction:** a forward is a promise about the future; a broken promise strands a universe mid-run at exactly the moment spot supply is scarce. Collateral is therefore table stakes for forwards from day one — not a response to abuse, but the thing that makes the instrument meaningful at all. Spot posture unchanged.

---

## 7. Explicitly out of scope (named to prevent scope creep)

- **Cash-settled futures / index-settled derivatives.** Require a deep, manipulation-hardened index. Revisit only if hedging demand is proven and spot depth sustains it. Possibly never.
- **Secondary trading / transfer of forwards.**
- **Interactive-class (low-latency SLA) forwards.**
- **Cross-margining, portfolio collateral, netting.**
- **Capability-key widening (quant/context/latency class)** — Wave 5 candidate, tracked separately.
- **Proprietary-model instruments.** Posted-price providers; the market covers open-source models only. Hosted prices enter only as the ceiling reference.

---

## 8. Build order & dependencies

```
Wave 2 (claim + settle + ledger)            [prerequisite]
  └─ Wave 3a token normalization            [1 dev-day: migration + RPC validation + tests]
       └─ Wave 3b spot index + quote API    [2 dev-days: index job + endpoint + MCP tool + tests]
            └─ Wave 4 forwards              [4–5 dev-days: schema + lifecycle RPCs + curve API + tests]
                 └─ §5 demand signal        [1 dev-day, flag-gated]
```

Each wave is independently shippable and independently useful: 3b is a standalone product (live open-model price feed) even if Wave 4 never ships.

---

## 9. Implementation status (2026-07-08)

The hard-correctness core is **implemented and adversarially reviewed**, transport-independent, in `tinyassets/paid_market/`: `index.py` (composite quote, pair-capped VWAP, window widening, ceiling clamp), `buckets.py` (UTC alignment, horizon, enumeration), `forwards.py` (state machine, capacity-reservation settlement with exact conservation). 75 tests in `tests/test_paid_market_core.py` incl. a 20k-case conservation sweep. Findings and two demonstrated-then-fixed exploits (A-2 thin-market index manipulation, B-1 profitable no-show griefing) are recorded in `docs/design-notes/2026-07-08-paid-market-adversarial-review.md`. Remaining work is transport: Supabase schema migrations 006/007, RPCs wiring these pure functions, quote/curve endpoints, MCP tool exposure (text block required), and the verification layer for reported token counts (review finding B-5).
