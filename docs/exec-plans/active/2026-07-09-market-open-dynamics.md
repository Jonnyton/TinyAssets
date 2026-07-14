# Market Open Dynamics — The Supply Curve Clears at Zero (2026-07-09)

**Status:** Binding amendment to Track E market mechanics (founder design, adopted over the earlier floating-base-price sketch). The market is a TRUE SUPPLY CURVE cleared at the marginal reserve — fully functional on day one at price zero.

## 1. Mechanism
- Every seller lists capacity with a **reserve price; default reserve = 0** (donation — BOINC/Folding@home precedent: volunteer idle compute is an established culture).
- Standing supply stacks by reserve into a curve. **Spot price := the marginal reserve at current utilization.** Demand within zero-reserve capacity -> price 0, all tasks simply run. Demand beyond it -> price walks UP the curve to the reserve tier that covers it. Nobody administers the price; the curve is the price.
- **Priority fee** (demand-side mirror): when a queue exists, buyers may bid above clearing to jump it. Latency-sensitivity prices itself.
- **Ceiling unchanged:** the walk-up terminates at the hosted-API price.

## 2. The volunteer lane (HARD RULE)
Zero-price work is NOT a $0 settlement. At reserve 0: no escrow, no fee (1% of zero), NO settlement rows — the paid-settlement modules correctly reject non-positive amounts and must not be forced. What survives at zero: gate verification, dispute-quality signals, and **reputation** — the early seller's real compensation and their queue-position edge when prices rise. Volunteer completions are journaled (utilization + reputation), not settled.

## 3. Quote amendment
The spot quote adds `clearing_reserve_micros` — the live marginal-reserve price (may be 0), computed from the standing curve vs current demand — published alongside the trade-history VWAP (which exists only once money moves). Two honest signals; never blend them.

## 4. Consequences adopted
- **Cold start dissolves:** "the market opens at zero" is a clearing, not a failure state. Day-one buyers get free compute (acquisition); day-one sellers earn reputation + curve position (honest, no promised earnings).
- Launch copy may truthfully say: **"Compute is free while there's surplus."** It is mechanism, not subsidy.
- Earnings calculator (discovery-flows §3) shows the honest pair: current clearing price + the demand curve that moves it. Resolves the supply-door sequencing tension without hype.
- Forwards coexist: guaranteed future capacity retains positive value (insurance) even when spot clears at 0.
- Sellers wanting money set reserves; donors donate; both coexist on one curve. No cannibalization problem — scarcity, when it comes, walks the price up automatically.

## 5. Opus notes
Implement the curve as reserve-sorted standing capacity per instrument; clearing computation is a read-path scan (cacheable). Volunteer-lane completions bypass escrow/ledger settlement adapters entirely — reputation and utilization journals only. Do not reintroduce an administered/floating base price; the earlier EIP-1559-style sketch is superseded by this note.
