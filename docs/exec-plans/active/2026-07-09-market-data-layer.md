# Market Data Layer — Screeners, Scanners, Explorer (2026-07-09)

**Status:** Binding design note. Exchanges win by being where everyone LOOKS: the decision-support layer is the product. Design law holds — the platform ships DATA PRIMITIVES (public honest feeds); screeners are LENSES (commons artifacts, defaults shipped on the website).

## 1. Data primitives (public read feeds — same surfaces for humans and universes)
Per instrument: clearing price (`clearing_reserve_micros`), VWAP + history, ceiling, forward curve, settled volumes, utilization, queue depth, seller count/concentration, aggregated supply-curve depth per price tier. Platform-wide: declared-demand aggregates (k-anonymized), capability mints + adoption, attribution/royalty flows, bounty-board value by domain, fab volumes by capability/geo, shuttle-pool fill. All unauthenticated, cached, staleness-stamped.

## 2. Default lenses (the four capital-allocation questions)
1. **Instrument screener** — filter/sort models by price, trend, utilization, forward spread, seller concentration, demand growth. Headline column: **ceiling discount** ("clears at 6% of hosted price") — the conversion argument as a number.
2. **Workflow cost optimizer** (buyer: "what do I convert to?") — price feed JOINED to the user's own graphs. **Conversion = REMIX, never a model-ID swap** (founder amendment 2026-07-09): every model wants different context shape/prompt idiom, so the optimizer generates a candidate branch remixed for the target model using **model adaptation profiles** — a commons artifact class of per-model context conventions the community maintains — then proves the candidate through the user's own gates before migrating. **Ships primarily as a STANDING GOAL** ("continuously remix to the cheapest model that still passes my gates") — retention artifact: "your universe cut costs 30% last month." Adaptation profiles join the commons seed list.
3. **Supply opportunity scanner** (seller: "what capacity do I build?") — utilization pressure + price walking the curve + forward premiums + the unfair signal: **declared future demand vs registered capacity** ("4,000 universes hold branches for X; capacity covers 60% — build here").
4. **Silicon targeting scanner** (designer: "what chip is worth taping out?") — rank models by silicon opportunity score = sustained demand volume x (clearing price - est. custom unit cost), crossover via the pinned `break_even_units`. The demo's live quote, generalized into a scanner.

## 3. Settlement explorer (the Etherscan analog)
Public, linkable pages for every settlement, pool fill, mint, and attribution flow — joined to on-chain escrow per the non-custodial constraint. Radical legibility is the trust half of the moat; a money platform that cannot be audited by a stranger is asking for faith it hasn't earned.

## 4. HARD RULES
- Declared-demand feeds: **k-anonymized aggregates ONLY** (Track E §5 privacy flag, now binding). No universe identifiable, ever.
- Supply curves publish as aggregated depth per tier — never individual reserves.
- Every estimated field carries `estimate: true` + staleness stamps (ceiling-feed discipline, generalized). Never fabricate liveness.
- One feed surface: website lenses and universe planning reads consume IDENTICAL public data. No privileged private feed — the exchange is Switzerland to information too.

## 5. Sequencing
Feeds land with their sources (clearing price with the curve, W3b; forwards curve with W4; demand aggregates behind the privacy pass; explorer with settlement). Default lenses are commons-seed work; the optimizer standing goal joins the archetype seed list (it is both a retention engine and honest recurring demand).
