# Paid-Market Core — Adversarial Review Record

**Date:** 2026-07-08
**Scope:** `tinyassets/paid_market/{index,buckets,forwards}.py` (pure logic, Track E Waves 3–4)
**Method:** two independent review passes with distinct attacker profiles, run against the code after the first green test suite. Both passes executed their candidate exploits as code before any fix was written; findings below include the demonstrated exploit output. (Disclosure: both passes were performed by the same Claude Fable 5 session in sequence, not by separate agents — treat this as structured self-review, and re-review before mainnet settlement.)

---

## Pass A — financial-math attacker

Profile: rounding exploits, dust theft, fee evasion, division-order errors, cliff discontinuities.

### A-1 (design, fixed pre-emptively): 95%-threshold payment cliff
The spec's original "≥95% delivered = delivered" reading, if applied to *payment*, lets sellers systematically skim the final 5% of every contract (deliver 95%, collect 100%). **Fix:** payment is always pro-rata; the threshold gates collateral slashing only. Enforced by `test_at_threshold_no_slash_but_prorata_payment` and the monotonicity sweep (`test_seller_payment_monotone_in_delivery` — delivering more never pays less, so no cliff anywhere on the curve).

### A-2 (CONFIRMED EXPLOIT, fixed): weight cap silently disengaged in thin markets
With the 25% pair-share cap, any market with ≤4 counterparty pairs made the water-filling fixed point infeasible (n·c ≤ 1), and the original code fell back to **raw volumes**. Demonstrated: 3 honest pairs at 5.0 + one wash pair with 1000× volume at 50.0 → published VWAP **49.87**. **Fix:** infeasible cap → equal pair weights; volume cannot buy influence in thin markets. Same scenario now publishes 16.25 (whale bounded at 1/n = 25% influence), and the ceiling clamp bounds the residual. Regression: `test_A2_thin_market_whale_bounded`.

### A-3 (accepted risk): dust-scale fee evasion
`fee = gross * fee_ppm // PPM` floors to 0 for any contract under 100 micros total (< $0.0001). Economically irrelevant; a per-contract minimum price would close it but contradicts the no-floor market memory. Documented, not fixed.

### A-4 (verified sound): rounding policy
Every division is a single floor with the remainder assigned by subtraction: seller_gross dust → buyer refund; fee dust → seller; slash dust → seller release. Conservation (`seller_net + fee + refund == total`; `released + slash == collateral`) is exact by construction, asserted inside `Settlement.check_invariants`, and swept over 20,000 randomized cases. Python ints are unbounded — no overflow class.

---

## Pass B — market-structure & state-machine attacker

Profile: griefing, wash trading, sybil economics, incentive misalignment, illegal state transitions.

### B-1 (CRITICAL, CONFIRMED EXPLOIT, fixed): buyer no-show griefing was *profitable*
Original settlement measured delivery against contract size. An attacker who buys a competitor's forward and submits **zero requests** produced `tokens_delivered = 0` → full buyer refund **plus** the entire slashed collateral. Demonstrated: 100 Mtok contract, attacker recovers 500M micros refund + 100M micros slash — the attacker *profits* from taking a rival's capacity off the market. **Fix:** capacity-reservation model. Settlement takes `tokens_requested`; the seller's obligation is `demand = min(requested, size)`, payment refunds only *unserved demand*, slash only on unserved demand below threshold. Buyer no-show → seller paid in full (use-it-or-lose-it, standard for reservations). Griefing now costs the attacker the full contract price. Regressions: `test_B1_noshow_griefing_unprofitable`, `test_B1_dribble_demand_griefing_bounded`.
**Schema consequence:** the `forwards` table and delivery accounting must record `tokens_requested` alongside `tokens_delivered` — buyer-submitted requests tagged `forward_id` count as demand whether or not they were served.

### B-2 (accepted risk, documented bound): sybil circumvention of pair caps
Pair caps raise wash-trading cost but sybil pairs (cheap wallets) restore weight share. Cost of attack: each wash trade round-trips the 1% fee + gas, so pushing the index to price P over volume V costs ≥ 0.01·P·V — nontrivial but not prohibitive. The real backstop is structural: (1) the **ceiling clamp** means the published VWAP can never exceed the hosted-API price, bounding upward manipulation absolutely; (2) **nothing settles against the index** (physically-settled forwards only; cash-settled futures are explicitly out of scope), so manipulation buys influence over a *reference* signal, not a payout. This bound must be re-derived before any instrument ever cash-settles against the index.

### B-3 (verified sound, rationale recorded): slash proceeds go to the buyer
If slashes flowed to the treasury, the platform would profit from seller defaults — a perverse incentive against fixing reliability. Slash compensates the harmed buyer; the treasury earns only its fee on actual payments.

### B-4 (verified sound): state machine and buckets
No transition reaches SETTLED without passing DELIVERING; terminal states are absorbing; unknown states rejected. Buckets are UTC-only (no DST class of bug), naive datetimes rejected loudly, `next_bucket_start` on an exact boundary returns the *next* bucket (consistent with strictly-future validation — the currently-running bucket is spot's job). Week buckets anchor Monday 00:00 UTC.

### B-5 (open, out of this module's scope): delivered-token count honesty
`tokens_delivered`/`tokens_requested` are reported quantities. A lying seller inflates served counts; a lying buyer's requests are their own telemetry. Cross-checks (deliverable-size heuristics, redundant sampling, dispute window) live in the transport/verification layer per spec §1 — flagged here so the pure-math layer's trust boundary is explicit: **this module computes correct settlements over honest inputs; it does not make inputs honest.**

---

## Result

75/75 tests green post-fix, including 20k-case conservation sweep, payment monotonicity, and named regressions for A-2 and B-1.
