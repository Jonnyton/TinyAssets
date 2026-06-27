# Legacy Content Inventory — what carries over from tinyassets.io

Source: live tinyassets.io site (host: GoDaddy Website Builder). Captured 2026-04-28. Live site stays as reference until new site launches.

## Token / Contract Addresses (tinyassets.io/contract-add)

The `ta` token is multi-chain — three live deploys.

### BASE Chain (primary post-rebrand)
- **Main Token Address**: `0x0BB570E30f0b3C5D909C08e3316Dade9C1Dc7fE0`
- **Token Address (all others)**: `0xa446E417c9379863bD279CE715De59a80879bAfE`
- Bridge: Axelar Bridge → https://app.squidrouter.com/ (or similar Axelar UI)
- Explorer: https://basescan.org/
- CTA: **BUY TINY**

### PulseChain
- **Token Address**: `0x92a242f94db176082Df4D386B366f4217ab7fAFd`
- Direct buy: https://pulsescan.finvesta.io/#/token/0x92a242f94db176082Df4D386B366f4217ab7fAFd
- CTA: **BUY NOW**

### Old BSC (legacy)
- **Token Address (old)**: `0x839108AaecB749e8F33cc68bb6D6323F61206322`
- Migration: "EXCHANGE NOW 1to1" via 1inch.io
- Explorer: https://bscscan.com/

## Site nav / link inventory (carry-over priorities)

| Link | Current target | Where it lives in new site |
|---|---|---|
| **Home** | tinyassets.io | `/` (landing) — replaced |
| **White Paper / GitHub** | (need to verify URL) | Footer link + /contribute page (split into "Read paper" + "github.com/Jonnyton/TinyAssets") |
| **Blog** | tinyassets.io/blog | Phase 2: `/blog` (RSS or Notion-driven). Phase 1: link out to current /blog |
| **Contract Add** | tinyassets.io/contract-add | `/economy` (Phase 1.5) — full token info; or `/token` standalone |
| **Tiny Alliance** | tinyassets.io/tiny-alliance | Footer link + dedicated page if substantive content (need to crawl) |
| **Market Price** | tinyassets.io/market-price | `/economy` integrated section (Phase 1.5); or footer link to live page |
| **Portfolio** | tinyassets.io/portfolio | `/economy` integrated section (Phase 1.5) — "Portfolio Backed Currency" lineage |
| **More** menu | (need to crawl) | Likely social/extra links |

## Pages crawled (final inventory)

### `/` (Home)
- Hero: "Portfolio Backed Currency" + Buy Tiny / Add Liquidity CTAs
- Sections (top to bottom): Price Discovery Tools (Market Price + Portfolio cards), Total Supply panel, Valuation Calculator, How to evaluate Tiny's Value, Market Cap vs NAV, How price is kept inline with NAV, Blog preview, Subscribe + socials, Contact form

### `/contract-add` (Contract Address)
- Three-column layout: BASE Chain · PulseChain · Old BSC Address
- All addresses + buy CTAs + explorer links (already captured above)

### `/tiny-alliance`
- Headline: "Join the Tiny Alliance"
- Subhead: "Send us a message or go straight to book an interview below"
- Form: Name*, Email*, Phone, "What Community Mission are you most passionate about?*"
- Below: "Schedule Interview to join the Tiny Alliance"
  - **Interview** — 30 mins, Free, BOOK
  - **Consultation** — 30 mins, Free, BOOK
- Phone in footer: **206-800-8906** (a second number 425-312-3861 also surfaced briefly)

### `/blog`
- Headline: "Blogs"
- One published post visible: "Getting Started"
- Otherwise empty — looks like only seed content

### `/portfolio`
- Headline: **"About Us"** (despite the URL being /portfolio)
- Hero image: 3D pie chart of investments / charts spread
- Likely contains the actual asset-portfolio-backing-the-currency narrative below the fold (didn't scroll deep due to browser hang)

### `/market-price`
- Headline: "Market Price"
- Two cards: **BASE** (blue circle icon) · **PulseChain** (gradient hexagon)
- Each card has a "MARKET PRICE" button — likely linking to DexScreener / DexTools / similar
- Section below: "Connect With Us"

### `/white-paper-github` — **404 PAGE NOT FOUND**
- Real broken link on the live site! The nav points to a URL that doesn't exist
- Either the slug is different (e.g. `/white-paper`) or there's no actual White Paper page yet
- → Recommend: replace nav link with `https://github.com/Jonnyton/TinyAssets` directly OR write a `/white-paper` page that wraps `PLAN.md` (the actual design truth doc)

## Footer chrome (legacy)
- Footer links: HOME · WHITE PAPER/GITHUB · CONTRACT ADD
- "Tiny Assets" title
- Phone: **206-800-8906**
- Copyright: "© 2025 Tiny Assets - All Rights Reserved."
- Branding: "Powered by GoDaddy Airo"

## Booking / scheduling system
- Live on `/tiny-alliance` — uses GoDaddy's built-in booking widget
- Two service types: Interview (30 min) and Consultation (30 min), both free
- Booking flow handles calendar, confirmation, etc. via GoDaddy
- → For new site: either keep linking out to GoDaddy booking, or replace with Cal.com / Calendly / a custom slot picker

## Hero copy (legacy)

- **Headline**: "Portfolio Backed Currency"
- **Subhead**: "Tiny derives its value from a diverse portfolio of assets, view assets and learn more below"
- **CTAs**: "BUY TINY" · "ADD LIQUIDITY"

## Stats currently surfaced
- **Total Supply**: 12,344,744,965 (with **VERIFY ON CHAIN** button)
- **Valuation Calculator** link
- **Market Cap vs NAV** explainer
- **How price is kept inline with NAV** (arbitrage mechanism)

## Educational content (legacy — to abridge or link out)
- "How to evaluate Tiny's Value" section
- "Market Cap vs NAV" — explanation of net asset value
- "How price is kept inline with NAV" — arbitrage explanation

→ Most of this gets compressed into a single paragraph in the new `/economy` page + linked to a TinyAssets Economy Paper if/when it lands.

## Marketing surfaces (carry over)
- **Subscribe** form (email signup, free)
- **Social links**: LinkedIn · TikTok · X · YouTube · Facebook · Instagram (and probably Telegram/Discord behind "More")
- **Contact form**: Name · Email* · Message
- **Tiny Assets chat widget** (GoDaddy bot — replace with our own contact + social links)
- **TrustedSite** badge (low priority — security trust seal)
- **Bookings** / **My Account** chrome (GoDaddy commerce features — drop entirely, not relevant to TinyAssets)

## Drop entirely from new site
- "Sign In / Create Account / Bookings / My Account / Signed in as: filler@godaddy.com" — leftover GoDaddy chrome from a Bookings setup that was never used
- Cart icon (top right) — no commerce surface

## Link types that need a home in the new site

| Item | Phase 1 home | Phase 1.5+ home |
|---|---|---|
| BASE chain contract address | Footer pill + /economy (Phase 1.5) | Full /economy page section |
| PulseChain contract address | (Phase 1.5 only) | /economy section |
| Old BSC contract address + 1inch migration | (Phase 1.5 only) | /economy section "Migration" |
| Total Supply (12.3B) | Footer ticker (Phase 1.5) or skip | /economy stats panel |
| BUY TINY CTA | Footer (Phase 1.5) — link to BASE explorer + buy interface | /economy primary CTA |
| ADD LIQUIDITY CTA | Phase 1.5 — same place as BUY TINY | /economy alongside BUY |
| Subscribe form | Phase 1 footer (mailto: → Buttondown / ConvertKit later) | Same |
| Contact form | Phase 1 footer (mailto: ops@tinyassets.io) | Same with backend |
| Social links | Phase 1 footer (LinkedIn / X / YouTube / etc.) | Same |
| White Paper link | Phase 1 nav or footer ("Read PLAN.md" → github URL) | Same |
| GitHub link | Phase 1 nav + Contribute CTA → github.com/Jonnyton/TinyAssets | Same |

## Open questions for host

1. **What's the URL of the actual White Paper?** Is it the GitHub README, PLAN.md, or a separate doc?
2. **Tiny Alliance** — what is it and what should the page say?
3. **Subscribe form backend** — Buttondown, ConvertKit, MailChimp, or roll your own?
4. **Contact form backend** — mailto: only for Phase 1, or wire up to Forms Spree / Netlify Forms / Formcarry?
5. **Hosting target conflict** — see WebSite/03-shipping-plan.md and WebSite/05-content-decisions-and-final-component-map.md. Spec says GitHub Pages, launch checklist says GoDaddy Website Builder, your earlier answer said custom HTML/JS on GoDaddy domain. Which?
6. **Multi-chain policy** — does the new site lead with BASE (newest) and treat PulseChain + BSC as alternates, or list all three equally?
