# Shipping Plan — Track B Phase 1: Landing-First

## Decisions locked
- **Stack:** SvelteKit per spec (`docs/specs/2026-04-18-web-app-landing-and-catalog.md` §1)
- **Adapter:** `adapter-static` for Phase 1 (just landing), upgrade to dual `adapter-static + adapter-node` in Phase 2
- **Hosting target:** Cloudflare → GitHub Pages (primary) + GoDaddy cPanel SFTP (fast fallback). Both per spec §3.1.
- **Lead positioning:** TinyAssets product (per host); token/Tiny Assets mentioned as the contributor reward layer, not the headline.
- **Legacy crypto pages:** Drop from main nav. Contract address + supply + token mechanics get a home (see § Contract Address Home below).

## Phase 1 scope (this push)
Ship just three SSG surfaces:
- **`/`** — Hero ("Summon the daemon"), 3-CTA (Connect / Host / Contribute), Live TinyAssets Surface section, How-it-works, Token & Rewards strip, Contact, Footer
- **`/connect`** — copy-MCP-URL widget, optional GitHub OAuth (deferred to Phase 2)
- **`/legal`** — placeholder page with license info (CC0 content / MIT platform), ToS + privacy stubs

Everything else from the 16-surface spec is **Phase 2+**.

## Phase 2+ (later, after Phase 1 ships)
- `/catalog/` + `/catalog/nodes/<slug>` + `/catalog/goals/<slug>` + `/catalog/branches/<slug>` — driven by exported catalog repo
- `/catalog/search` — needs Supabase + embedding endpoint
- `/host` — needs OS-detect + tray installer artifacts
- `/contribute` — needs GitHub API client
- `/status` — needs Supabase Realtime channels live
- `/editor/*`, `/earnings`, `/admin`, `/account` — auth-gated, need Supabase Auth + RLS

## Contract Address Home — host decision needed
The legacy tinyassets.io has Tiny Assets contract address surfaced via the editor. The new spec doesn't have a "Token" page. Options for where the contract address lives in Phase 1:

| Option | Where | Pros | Cons |
|---|---|---|---|
| **A. Footer pill** (recommended) | Sticky in footer: "Contract: 0x...8abc · Verify on chain ↗" | Always visible, low chrome cost | Investors expect a richer page |
| B. `/legal` token-info section | Inside legal page | Clean, off-main-nav | Hard to find |
| C. Dedicated `/token` page | New SSG page, kept out of nav, linked from footer | Right home for full info: supply, contract addr, NAV mechanics, "Buy Tiny" pointer | Adds Phase 1 scope (~0.3 day) |
| D. Inside Token & Rewards section on `/` | Just on the homepage | Simple | Spec'd treasury config implies on-chain truth that needs a real page eventually |

**Recommendation: A (footer) for Phase 1, C (`/token`) added in Phase 1.5 as a small follow-on.** Lets investors find the contract today; gives space for the richer page once we know what they actually need.

## Project structure (SvelteKit)
```
WebSite/
├── 00-context.md
├── 01-merge-plan.md         (early — superseded by 02 + 03)
├── 02-deep-dive-findings.md
├── 03-shipping-plan.md      (this file)
├── design-source/           ← host drops Claude design export here
└── site/                    ← SvelteKit project root
    ├── package.json
    ├── svelte.config.js
    ├── vite.config.js
    ├── .gitignore
    ├── src/
    │   ├── app.html
    │   ├── app.css
    │   ├── routes/
    │   │   ├── +layout.svelte         (nav + footer + theme)
    │   │   ├── +page.svelte           (landing /)
    │   │   ├── connect/+page.svelte   (/connect)
    │   │   └── legal/+page.svelte     (/legal)
    │   ├── lib/
    │   │   ├── components/
    │   │   │   ├── Hero.svelte
    │   │   │   ├── TierCTAs.svelte
    │   │   │   ├── TinyAssetsShowcase.svelte
    │   │   │   ├── HowItWorks.svelte
    │   │   │   ├── TokenStrip.svelte
    │   │   │   ├── ContactForm.svelte
    │   │   │   └── ContractPill.svelte
    │   │   └── content/
    │   │       └── token-info.json    (contract addresses, supply, links — single source of truth)
    │   └── styles/
    │       └── tokens.css             (parchment palette, dark chrome, typography)
    └── static/
        ├── logo.svg
        ├── og-image.png
        └── favicon.png
```

## Build + deploy commands (host runs these locally for now)
```powershell
cd C:\Users\Jonathan\Projects\TinyAssets\WebSite\site
npm install
npm run dev          # local dev server on http://localhost:5173
npm run build        # static output in build/
npm run preview      # preview the static build
```

**Deploy (Phase 1, manual):** Upload `build/` to GoDaddy cPanel via SFTP. Real CI deploy from spec §3.1 lands in Phase 1.5.

## Pre-build dependencies on host
Before we can build:
1. **Node.js 20+ installed** on Windows (`node --version` should report ≥20)
2. **Git available** in PowerShell PATH (`git --version`)
3. **Claude design source exported** and dropped into `WebSite/design-source/` (host action — pending)

I can check #1 and #2 via shell. #3 requires you.

## Phase 1 ship checklist
- [ ] Design source landed in `design-source/`
- [ ] Node.js verified on host
- [ ] SvelteKit project scaffolded in `site/`
- [ ] Hero adapted from Claude design
- [ ] 3-CTA tier flow built
- [ ] TinyAssets showcase ported (parchment diagrams, at least 1 workflow)
- [ ] Token strip with contract pill
- [ ] Contact form (mailto fallback for Phase 1; real backend Phase 2)
- [ ] /connect page with copy-URL widget
- [ ] /legal placeholder
- [ ] Static build succeeds (`npm run build`)
- [ ] Lighthouse SEO ≥ 95 on landing
- [ ] LCP ≤ 2.5s on simulated 3G
- [ ] Host previews build locally
- [ ] Host deploys to GoDaddy cPanel via SFTP
- [ ] DNS/Cloudflare confirmed pointing right

## Open host decisions (need answers before scaffold finalizes)
1. Contract address home: A vs C vs both? (recommendation: both — A now, C in Phase 1.5)
2. Approved logo file? (or use the cube logo from current tinyassets.io as-is)
3. Real GitHub URL for "View on GitHub" button (currently unknown)
4. Real "Connect to MCP" target — is it just `tinyassets.io/mcp` URL to copy, or a deeper docs page?
5. Contact form recipient email
