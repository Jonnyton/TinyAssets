# Legal Pass — SEC 2026 + CLARITY Act framing

**Status:** Draft v0. NOT legal advice. Best-effort defaults populated for prototype ship; substantive counsel review required before any of the following: (a) any new public-facing token offering, (b) growth past USD 1k cumulative paid-market volume per user, (c) listing on any centralized exchange, (d) any non-US-resident user signup, (e) Phase 8 DAO governance go-live.

A securities lawyer with crypto practice must independently confirm or amend every default below before public launch. See bottom of doc for confirm checklist.

## 1. Regulatory landscape (Apr 2026)

### SEC "Project Crypto" framework
- April 2026 interpretive release defines five token categories: digital commodities, digital collectibles, digital tools, payment stablecoins, digital securities.
- A token-safe-harbor pathway has been signaled (Atkins remarks, March 2026).
- Withdrawal of SAB 121 (custody accounting) reduced exchange-side friction.

### CLARITY Act (H.R. 3633) status
- House passed July 2025 (294-134).
- Senate parallel markups in Banking + Agriculture committees; Banking eyeing late-April 2026 markup.
- Stablecoin-yield issue resolved: passive yield prohibited, activity-based rewards permitted.
- Target passage: before Nov 2026 midterms.
- Mature-blockchain-system carve-out: once a network meets decentralization + functional-use criteria, the underlying token is not a security.

### How `ta` fits

`ta` is positioned as **digital tool / digital commodity**:
- Necessary to participate in the TinyAssets paid-market.
- Value derives from programmatic operation (1% fee accrual, mint on cleared outcome gates, slash on fraud).
- Holders gain utility (place paid bids, run a daemon, vote DAO governance), not passive return.
- Activity-based rewards (CLARITY-compatible). No passive yield.
- Existing 12.34B supply was minted via the original tinyassets contract; no new ICO is being conducted.

---

## 2. Anticipated answers to the 15 items

Each item below has a **default** and a **rationale**. Counsel may revise. Each is keyed to a `confirm:` checkbox at the end.

### Item 1 — Token classification
- **Default:** `ta` is a **digital tool / digital commodity** under SEC 2026 Project Crypto. Not a security under Howey because (a) no expectation of profit derived from efforts of others, (b) rewards are activity-based for users' own work, (c) value drivers are programmatic and protocol-deterministic.
- **Rationale:** Mirrors Atkins-era SEC posture on utility tokens. Avoids Howey by not promising appreciation, not pooling investor funds, not depending on a managerial team's success for token value.
- **Risk:** SEC could still pursue an enforcement action — anti-fraud authority is preserved regardless of category. Mitigation: never make appreciation/yield claims; document protocol determinism.

### Item 2 — Mature-blockchain-system test
- **Default:** Document target criteria (likely from CLARITY Act final text):
  1. **Decentralization** — no single entity holds ≥10% of supply, governance distributed across ≥1000 addresses, multi-sig treasury (5-of-9 minimum).
  2. **Functional-use** — protocol has been live ≥12 months with ≥1000 monthly active wallets and ≥10000 paid-market settlements.
  3. **Open source** — platform code MIT-licensed and public, smart contracts source-verified on relevant block explorers.
  4. **Independent operation** — protocol can continue operating without any single party's involvement (multiple daemon hosts, multi-region MCP gateway).
- **Rationale:** Tracks the most likely shape of CLARITY's mature-blockchain test based on the House-passed bill text and analogous DOJ/SEC guidance.
- **TinyAssets path:** Phase 6 (outcome ranking) + Phase 7 (settlement contracts) + Phase 8 (DAO governance live) get us to maturity. ETA per existing roadmap.

### Item 3 — Geo-restrictions
- **Default:** Block:
  - **OFAC comprehensively-sanctioned jurisdictions:** Cuba, Iran, North Korea, Russia (Crimea + DNR/LNR + occupied regions), Syria.
  - **PRC** (crypto-trading ban).
  - **Any jurisdiction** where the local regulator has explicitly prohibited utility-token transactions.
- **US-state review pending:** New York (BitLicense scope), Texas (state-level guidance still evolving — flag for counsel).
- **EU:** Allow with MiCA-compliant disclosures (utility-token framework still settling — review pre-launch).
- **Enforcement:** Wallet-connect screening at the MCP gateway via Chainalysis or TRM (real-time + daily batch refresh) + self-declared geo-attestation at first paid-market action.
- **Rationale:** Conservative defaults. Conservative blocks > under-blocking + later enforcement action.

### Item 4 — KYC/AML
- **Default:**
  - **Tier-1 chatbot users** (browse, free workflow runs): no KYC.
  - **Tier-2 daemon hosts**: KYC at cumulative lifetime paid-market threshold of **USD 1,000** (Sumsub, Persona, or Onfido).
  - **Treasury operations**: full KYC + accredited-investor verification where applicable.
- **Rationale:** US FinCEN money-transmitter guidance (FIN-2019-G001) suggests crypto exchanges and "anonymizing service providers" need MSB registration. A peer-to-peer paid-market with no platform custody likely doesn't trigger MSB at v0, but threshold KYC keeps us defensible if enforcement posture shifts.
- **Prototype short-cut:** Cap paid-market activity below $1k per user at v0 launch — defers KYC integration until counsel confirms requirements.

### Item 5 — OFAC sanctions screening
- **Default:** **Chainalysis Sanctions API** (free tier suffices for prototype) screens at wallet-connect; daily batch refresh of all registered wallets via Chainalysis or TRM; block writes to/from any flagged address.
- **Rationale:** Industry standard. Compliance with OFAC's 2023 advisory on virtual currency sanctions screening.

### Item 6 — Existing-holder migration risk
- **Default:** The legacy "Portfolio Backed Currency" framing on `tinyassets.io` (current published site) does pose a backward-looking risk. Mitigation steps:
  1. **Public deprecation memo** posted on legacy site before new site launches: "Effective [date], the project is repositioned as a digital-tool utility token. The phrase 'Portfolio Backed Currency' is deprecated. No managed asset pool exists or has existed."
  2. **No swap, no airdrop, no new offering** — existing balances preserved 1:1 across BASE, PulseChain, BSC.
  3. **Holder-communication channel** — email-list or on-chain-message via the contract — explicitly tells holders the rebrand isn't a swap.
  4. **Document the rebrand** as a public-record memo in the GitHub repo.
- **Risk left open:** Pre-rebrand purchasers who relied on the old framing could conceivably claim misrepresentation. Counsel should evaluate whether any disclosure/repurchase obligation exists. Time-bar (statute of limitations) typically 3-5 years for misrepresentation; the contract has been live since 2024, so most exposure is recent.

### Item 7 — DAO governance
- **Default at v0:** DAO is **informal** — votes are advisory only, non-binding. Real-world authority lives with the operating entity until Wyoming DAO LLC is filed.
- **Target structure:** **Wyoming DAO LLC** (Wyo. Stat. § 17-31-101 et seq.) before Phase 8 go-live. Provides limited liability for voters, recognized legal personality.
- **Voter liability at v0:** Limited to `ta` staked in the vote per smart-contract rules. No personal liability claim is recognized by any clause on the site.
- **Vote scope (smart-contract-encoded only):**
  - Which goals are canonical in the public catalog.
  - Which third-party verifiers count for outcome-gate clearance.
  - Which outcome-gate ladders qualify for `ta` minting.
  - Treasury allocations within the DAO-controlled multi-sig.

### Item 8 — Privacy / GDPR / CCPA
- **Default:** Concept-public / instance-private / never-training-data posture (already in `/legal`). Add:
  - **Data Subject Access Request (DSAR)** flow via `legal@tinyassets.io`.
  - **Right to be Forgotten** per GDPR Article 17 / CCPA — 30-day grace-window deletion at `/account`.
  - **Cookie consent banner** if Plausible analytics goes live (Plausible doesn't require one but better to have).
- **Rationale:** GDPR + CCPA + UK DPA cover most likely user-locations.

### Item 9 — DMCA agent registration
- **Default:** File DMCA Agent Designation with US Copyright Office at <https://dmca.copyright.gov> — $6 fee, online form. Designate `dmca@tinyassets.io` and physical address (operating-entity HQ).
- **Rationale:** Required to qualify for DMCA safe harbor under 17 U.S.C. § 512.

### Item 10 — Choice of law / dispute resolution
- **Default:**
  - **Governing law:** State of Delaware, USA (without regard to conflict-of-laws).
  - **Dispute resolution:** **JAMS binding arbitration** in Delaware. **Individual claims only** (class-action waiver). **Mass-arbitration coordination prohibited** (avoid Tornado-Cash-style coordinated bombardment). Small-claims-court carve-out preserved.
  - **Venue for injunctive relief:** State and federal courts in Delaware.
- **Rationale:** Delaware = US business-law standard; predictable, well-known to counsel. JAMS = standard alternative for tech companies. Class-action waiver is enforceable in most US states post-AT&T v. Concepcion.

### Item 11 — Liability cap
- **Default:** Lesser of (a) fees paid to us in the 12 months preceding the claim, or (b) **USD 100**. Disclaim consequential, indirect, special, punitive damages. No exclusion for willful misconduct or gross negligence (some jurisdictions don't permit those exclusions).
- **Rationale:** SaaS-industry standard. Not enforceable as a complete bar in NJ, VA, CA-consumer-claims, or EU jurisdictions — disclose accordingly.

### Item 12 — Indemnification
- **Default:** **Asymmetric mutual indemnity:**
  - **User indemnifies platform** for: misuse of the service, IP infringement of user-provided content, sanctions violations, false geo-attestation.
  - **Platform indemnifies user** for: IP infringement of platform code (within the MIT license — i.e. not for fork-induced infringement), platform-caused unauthorized data disclosure.
  - Cap on platform indemnity = same as liability cap.

### Item 13 — Force majeure
- **Default:** Suspends performance for: blockchain-network events (chain reorgs, RPC outages, gas spikes >5× baseline, hard forks), cyberattacks, regulatory action prohibiting operation, infrastructure-provider outages (Cloudflare, Supabase, Fly.io, GitHub), acts of God, war, civil unrest, pandemics. 30-day suspension permitted; pro-rated refund of any prepaid fees if longer.

### Item 14 — Children's privacy / COPPA
- **Default:** Service is **not directed at children under 18**. Minimum age **18+** for paid-market participation (matches most crypto platforms). Self-declared age-gate at wallet-connect. If we knowingly collect data from a minor, delete on request.
- **Rationale:** Crypto + financial transactions = adult-only. Avoids COPPA complications entirely.

### Item 15 — Tax disclaimer
- **Default:** Site provides no tax advice. Daemon hosts who earn ≥USD 600/year in `ta` will receive a year-end CSV summary for self-reporting; **we do not file 1099-MISC at v0** (that's a Phase 2 commitment once operating entity is formed). International users responsible for own jurisdiction's tax treatment. Recommend consulting a qualified tax professional.
- **Rationale:** Form 1099-MISC threshold is $600 under current IRS guidance. CSV provision is a courtesy, not a legal substitute for 1099-MISC.

---

## 3. Counsel-confirm checklist

Each item below needs an independent legal review and either a 🟢 confirm or 🔴 amend response. Block public launch on any 🔴.

```
[ ] 1. Token classification — ta as digital tool / commodity
[ ] 2. Mature-blockchain-system criteria draft
[ ] 3. Geo-restriction block list
[ ] 4. KYC/AML thresholds + provider
[ ] 5. OFAC screening provider + cadence
[ ] 6. Existing-holder migration disclosures
[ ] 7. Wyoming DAO LLC formation timing
[ ] 8. DSAR / GDPR Article 17 flow
[ ] 9. DMCA agent designation filing
[ ] 10. Delaware governing law + JAMS arbitration
[ ] 11. Liability cap enforceability per jurisdiction
[ ] 12. Indemnification scope
[ ] 13. Force majeure clause completeness
[ ] 14. Minimum age 18 + age-gate UX
[ ] 15. Tax-reporting commitments
```

---

## 4. What's safe to ship now (prototype)

With the defaults above, the prototype site can ship publicly **provided**:
- All token language is utility/digital-tool framed (no investment claims). ✓ done.
- `/legal` page is published with the full Draft-v0 disclosures. ✓ done.
- Footer links to `/legal` from every page. ✓ done.
- No paid-market transactions are processed at v0 — only browse + connect + view. (If paid-market goes live, KYC threshold + OFAC screening must be in place first.)
- A public deprecation memo for "Portfolio Backed Currency" goes on the legacy site before new-site DNS cutover.
- Counsel review is initiated within **30 days** of public launch.

## 5. What MUST wait for counsel

- **Any new ta offering** (sale, swap, airdrop, exchange listing).
- **Paid-market go-live** with real money flowing.
- **Wyoming DAO LLC** formation and Phase 8 binding governance.
- **International expansion** beyond informational browse use.
- **Any change to liability cap or arbitration clause** below the defaults.
