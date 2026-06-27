# Merge Plan — TinyAssets site (lead) + Tiny Assets token (secondary)

## Decisions locked in
- **Lead product:** TinyAssets (the MCP tooling / branchable AI workflows product)
- **Secondary:** Tiny Assets token as a future utility-rewards mechanism — present, not centered
- **Stack:** Plain HTML / CSS / JS, single static site (no build step). Portable to GoDaddy hosting or any static host.
- **Project root:** `C:\Users\Jonathan\Projects\TinyAssets\WebSite\`
- **Visual direction:** parchment / dusty-rose / sage diagrams (from Claude design) inside a dark ink + ember chrome (navbar/hero) — kept consistent with current Tiny Assets purple-on-dark brand where it makes sense

## Folder layout (proposed)
```
WebSite/
├── 00-context.md          ← what we found
├── 01-merge-plan.md       ← this file
├── design-source/         ← user drops Claude design export here
├── site/                  ← the actual website source
│   ├── index.html
│   ├── styles.css
│   ├── scripts.js
│   ├── assets/            ← images, fonts, logo
│   └── pages/             ← whitepaper.html, blog.html, etc. (later)
└── content/               ← raw content extracted from tinyassets.io for re-use
```

## Information architecture — new site
A long-scroll homepage with these sections, in order:

1. **Hero** — TinyAssets as the lead
   - Headline: *"TinyAssets for AI work that can be inspected, improved, and rewarded"* (carry over from GoDaddy draft)
   - Sub: live MCP tools, branchable workflows, community bug reports, gates, future utility-token rewards
   - CTAs: **Connect to MCP** (primary, ember/coral) · **View on GitHub** (secondary, outline)
   - Visual: dark ink background; subtle parchment accent strip

2. **Live TinyAssets Surface** — the showcase
   - Embed/port the Claude design's interactive workflow diagrams (parchment cards, dusty-rose execution bands, sage active nodes)
   - TinyAssets switcher: Dev-team scaling · Book publishing pipeline (carried from Claude design)
   - Click any node → drawer with reads/writes/lifecycle state
   - Tweaks toolbar: annotations on/off, lifecycle animations on/off

3. **How it works** — three short pillars
   - **Inspect** — see every step, every fork
   - **Improve** — community bug reports, gates
   - **Reward** — Tiny token bridge (segue to next section)

4. **Tiny Assets — the rewards layer** (token section, secondary)
   - Brief: contributor work in TinyAssets earns Tiny Assets utility tokens
   - Live stats row: Total Supply (12,344,744,965), Market Cap vs NAV, Verify on Chain
   - Two cards: **Market Price** · **Portfolio** (carry imagery from old site)
   - CTAs: **Buy Tiny** · **Add Liquidity** · **Valuation Calculator**
   - One-paragraph "Portfolio Backed Currency" explanation (much shorter than old site)

5. **Resources**
   - White Paper (link) · GitHub (link) · Contract Address (with copy button) · Tiny Alliance · Blog
   - These live in the nav too; this section gives them visual weight

6. **Subscribe + Socials**
   - Email signup
   - LinkedIn · TikTok · X · YouTube · Facebook · Instagram (carry from old site)

7. **Contact**
   - Form: Name · Email · Message (carry from old site)

8. **Footer**
   - Logo, tagline, copyright, secondary links (privacy, terms)

## What carries over from the old site
- Tiny Assets cube logo (orange) — keep for brand continuity
- Total supply number, contract address, market cap mechanics
- "Portfolio Backed Currency" explanation (compressed)
- Buy Tiny / Add Liquidity CTAs
- Verify on Chain link
- Valuation Calculator link
- Blog (link out for now; embed RSS later)
- Subscribe form
- Social links
- Contact form

## What carries over from the Claude design
- The parchment / dusty-rose / sage palette for diagram cards
- The workflow showcase content (dev-team scaling diagrams, book publishing pipeline, gate routing matrix)
- "Summon the daemon" / Fraunces serif accents (sparingly — only for the showcase section, not the main hero)
- Interaction patterns: workflow switcher, clickable nodes, detail drawer, tweaks toolbar

## What gets dropped or revised
- "Portfolio Backed Currency" as the main headline → demoted to the token section
- Multiple repeated hero text instances (the live site has the headline four times due to slider — clean to one)
- Old site's filler GoDaddy account chrome (Sign In / Bookings / My Account / "Signed in as filler@godaddy.com") — remove entirely
- Old "How to evaluate Tiny's Value" / "Market Cap vs NAV" / "How price is kept inline with NAV" three-section explainer → compress to one paragraph + link to White Paper for full version
- The GoDaddy live chat widget — replace with simple Contact form / Discord link

## Build order
1. Receive Claude design export (user) → place in `design-source/`
2. Extract palette, typography, diagram primitives from the design source
3. Scaffold `site/index.html` shell with sections 1–8 (empty, with comments)
4. Build hero + TinyAssets Surface (lift from design source as-is, adapted)
5. Build Tiny Assets token section (new — combining old content + new look)
6. Build remaining sections (Resources, Subscribe, Contact, Footer)
7. Pull image assets from old site into `site/assets/`
8. Test responsiveness, smooth scrolling, drawer interactions
9. Document deploy steps for GoDaddy static hosting

## Open questions / things I'll need from you later
- Logo files (SVG ideal) — can grab from tinyassets.io if you don't have separate files
- Real GitHub URL for the TinyAssets project (the buttons currently go to placeholders)
- Real "Connect to MCP" target — is this a doc page, install command, or `claude mcp add ...` snippet?
- Real contract address (currently shows nothing on the homepage of live site)
- Confirmation when Claude design source is dropped into `design-source/`

## Hosting note (GoDaddy)
- GoDaddy "Website Builder" plan does NOT support uploading custom HTML/JS — you'd need GoDaddy's "cPanel Hosting" / "Linux Hosting" plan to deploy a custom static site at your domain
- If you only have Website Builder, alternatives: rebuild inside their editor (limited), or move DNS to a free static host (Netlify/Vercel/Cloudflare Pages) and keep the .io domain
- I'll flag this when we get to deploy
