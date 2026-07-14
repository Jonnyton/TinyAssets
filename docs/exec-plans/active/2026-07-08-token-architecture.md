# Token Architecture — Stablecoin × TINY (2026-07-08)

**Status:** Design note + implemented fund math (`tinyassets/paid_market/fund.py`; 155-test suite total). **LEGAL GATE: nothing in this document ships to public availability without counsel sign-off — see §5.**

## 1. The wall

Two tokens, opposite sides of a hard wall, and the wall is the design:

| | Stablecoin | TINY |
|---|---|---|
| Role | Unit of account + settlement rail | Claim on the platform's productive asset pool |
| Appears in | Every price, cap, escrow, collateral, refund, payout across all markets (E/F/G/H/I) | Nowhere in any settlement path — `fund.py` is imported by no market module, by design |
| Issuance | **Not ours.** Use an existing regulated stablecoin (USDC, native on Base). Self-issuing a payment stablecoin is licensed, reserve-audited activity (GENIUS Act; MiCA) — enormous compliance surface for zero product benefit | Minted ONLY against contributed value at NAV; burned on redemption at NAV. No discretionary mint path exists in code |

Why the wall is load-bearing: every market module prices in integer micros of a *stable* unit. A volatile settlement token would make forward prices (compute price × currency bet) meaningless, break cap semantics, and poison the index. Conversely, keeping TINY out of payments keeps day-to-day platform use free of securities questions — users can buy compute, train models, and sell capacity without ever touching TINY.

## 2. How the fund fills (TINY's AUM across the whole project)

- **The 1% treasury fee** — already computed in every settlement across spot, forwards, training, pools, and fabrication — flows in as stablecoin (`record_fee_inflow`: AUM rises, supply doesn't, NAV accretes to holders).
- **Treasury positions**: fractional shares in pooled models (Track H), dataset revenue-share legs (Track G ppm), hardware-design attribution (Track I). TINY thereby becomes an index on the model economy the users themselves build.
- **AUM transparency**: holdings visible on-chain in the mint-authority wallet — the ETF instinct, kept.

## 3. Fund discipline (implemented, tested)

- **Mint at NAV only**, floored (contributor never receives above-NAV value); genesis bootstraps 1:1 and prices any pre-seeded treasury into the first mint rather than gifting it.
- **Redeem at NAV only**, floored; full wind-down pays exact AUM (no stranded assets).
- **Rounding always favors the fund**: a 5,000-case adversarial sweep proves a mint→redeem cycle can never extract value — high-frequency dust-skimming is arithmetically impossible.
- **Only non-mint AUM increase is fee inflow.** There is no code path for printing.

## 4. Valuation rule (the honest hard part)

Track H shares are deliberately non-transferable (its own legal gate), so most fund positions have **no market price**. Marking them to model would let NAV be inflated by optimism. Binding rule: **stable reserves at face + productive positions valued by realized trailing cash flow only** — every input auditable from the settlement ledger. Conservative NAV understates; it never lies. Valuation computation is a ledger/reporting job; `fund.py` takes AUM as input and never guesses.

## 5. Legal gates (named, not buried)

1. **TINY is very plausibly a security/fund interest** (value from a managed asset pool + expectation of profit from others' efforts). Public mint/redeem availability, marketing language, and jurisdictional availability are counsel decisions. Until sign-off: treasury-internal accounting only.
2. **Stablecoin**: resolved by not issuing one (§1). If self-issuance is ever revisited, it is a licensing project first.
3. This gate stacks with Track H §3 (share non-transferability) — the same counsel engagement should cover both.

## 6. Founder decisions pending

Redemption gating (open vs. windowed), whether TINY carries governance weight, treasury position policy (what % of fee inflow buys model/dataset positions vs. stays in reserves), and the genesis treasury contents.

## 7. Current-state setup (corrected 2026-07-08 with founder's actual figures)

Actual state: mint-authority wallet holds ~$10k of MIXED on-chain assets — **fully backing the entire supply**. A separate wallet holds the founder's ~99% of tokens (legitimate: he contributed the AUM) plus ~$2.5k deployable for liquidity. No unbacked supply exists; no burn is needed.

**Binding rules:**
1. **Fund assets never provide liquidity for TINY** (unchanged — the founder's original instinct; AUM in a TINY pair bleeds backing to arbitrage and creates the reflexive spiral).
2. **Mixed-asset NAV requires live pricing + an entry/exit fee.** Volatile backing means NAV floats (intended ETF behavior), but mint/redeem at stale prices is arbitrage against holders. Defense (implemented): `mint_at_nav_with_fee` / `redeem_at_nav_with_fee` — the fee ACCRUES TO AUM (never leaves the fund), a round trip is strictly unprofitable, and full wind-down is fee-exempt and pays exact AUM. Suggested band 0.3–1% (3_000–10_000 ppm).
3. **Redemptions from mixed assets:** either maintain a liquid sleeve with `redemption_capacity_base_units` (instant up to sleeve, queue beyond) or redeem IN-KIND (pro-rata slice of each asset — avoids forced selling entirely; cleanest at current scale). Founder decision.
4. **The pool is personal and seeded AT NAV:** $2.5k USDC + $2.5k-worth of the founder's tokens at current NAV → ~$5k depth against a $10k fund. Seeding off-NAV gifts the difference to the first arbitrageur. Remaining founder tokens are stake, not inventory — they stay out of the pool. Pool downside bounded at the personal $2.5k; fund untouched; NAV±fee arbitrage pins the pool price automatically. Larger flows route through mint/redeem — the fund itself is the primary liquidity.
5. Founder concentration dilutes fairly and automatically as others mint (NAV-priced mints cannot dilute incumbent value). No action needed.
